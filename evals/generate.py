"""Generate Russian single-turn RAG goldens with DeepEval Synthesizer."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from deepeval.models import OpenRouterModel
from deepeval.synthesizer import Synthesizer
from deepeval.synthesizer.config import EvolutionConfig, StylingConfig
from deepeval.synthesizer.types import Evolution

from app.privacy import PiiSanitizer
from app.schemas.knowledge_schema import KnowledgeDocumentCreate
from app.service.knowledge_ingestion_service import chunk_text

CORPUS = Path("docs/RAG/Agent_memory.txt")
OUTPUT = Path("evals/datasets/generation/golden.dataset.json")
EVOLUTIONS = {
    Evolution.REASONING: 0.25,
    Evolution.MULTICONTEXT: 0.20,
    Evolution.CONSTRAINED: 0.15,
    Evolution.COMPARATIVE: 0.15,
    Evolution.HYPOTHETICAL: 0.10,
    Evolution.CONCRETIZING: 0.10,
    Evolution.IN_BREADTH: 0.05,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--model", default="google/gemini-3.1-flash-lite")
    parser.add_argument("--max-goldens-per-context", type=int, default=2)
    parser.add_argument("--num-evolutions", type=int, default=2)
    parser.add_argument("--limit-contexts", type=int)
    args = parser.parse_args()
    if not args.model or not os.getenv("OPENROUTER_API_KEY", "").strip():
        parser.error("Set OPENROUTER_API_KEY and --model (or AG2_MODEL)")
    if args.max_goldens_per_context < 1 or args.num_evolutions < 0:
        parser.error("--max-goldens-per-context must be positive; evolutions >= 0")
    if args.limit_contexts is not None and args.limit_contexts < 1:
        parser.error("--limit-contexts must be positive")
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}; choose a new --output")

    corpus_bytes = args.corpus.read_bytes()
    rows = json.loads(corpus_bytes)
    if not isinstance(rows, list) or not rows:
        raise ValueError("Corpus must be a non-empty JSON list of knowledge documents")
    documents = [KnowledgeDocumentCreate.model_validate(row) for row in rows]
    documents = documents[: args.limit_contexts]
    pii = PiiSanitizer()
    contexts = [
        [
            pii.sanitize_text(f"[Источник: {document.title}]\n{chunk}").text
            for chunk in chunk_text(document.content)
        ]
        for document in documents
    ]
    if any(not context for context in contexts):
        raise ValueError("Every document must contain non-blank content")
    source_files = [str(args.corpus)] * len(contexts)
    PiiSanitizer.ensure_safe([contexts, source_files])
    model = OpenRouterModel(
        model=args.model,
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
    )
    synthesizer = Synthesizer(
        model=model,
        async_mode=True,
        max_concurrent=10,
        evolution_config=EvolutionConfig(
            num_evolutions=args.num_evolutions,
            evolutions=EVOLUTIONS,
        ),
        styling_config=StylingConfig(
            scenario="Русскоязычные клиенты автосалона консультируются перед покупкой.",
            task=(
                "Задавать вопросы об автомобилях и услугах, где ответ только по "
                "предоставленному контексту. Проверять ограничения, условия, "
                "сопоставление фактов. Не придумывать отсутствующие сведения."
            ),
            input_format="Естественный самостоятельный вопрос клиента на русском языке.",
            expected_output_format=(
                "Краткий полноценный ответ на русском языке с необходимыми фактами "
                "и оговорками из контекста, без выдуманных цен и гарантий наличия."
            ),
        ),
    )
    goldens = synthesizer.generate_goldens_from_contexts(
        contexts=contexts,
        source_files=source_files,
        include_expected_output=True,
        max_goldens_per_context=args.max_goldens_per_context,
    )
    if not goldens:
        raise ValueError("Synthesizer returned no goldens")
    payload = []
    for index, golden in enumerate(goldens, start=1):
        if not golden.input.strip() or not (golden.expected_output or "").strip():
            raise ValueError("Generated goldens must have an input and expected_output")
        golden.name = f"synthetic_{index:04d}"
        golden.additional_metadata = {
            **(golden.additional_metadata or {}),
            "split": "test",
            "answerable": True,
            "generator_model": args.model,
            "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        }
        payload.append(pii.sanitize_value(golden.model_dump(mode="json")))
    PiiSanitizer.ensure_safe(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # save_as() in DeepEval 4.3.3 drops names and Evolution metadata.
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"Saved {len(payload)} goldens to {args.output}. Review before evaluation.")


if __name__ == "__main__":
    main()
