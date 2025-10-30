"""Automate the creation of tailored job applications.

This module provides a command line program that ingests a structured
configuration file describing the candidate, the job posting, and any
custom questions.  It generates a ready-to-submit Markdown summary of the
application and a manifest describing supplemental material such as
attachments.  The script is designed to reduce repetitive work when applying
for multiple roles that share similar information.

Example
-------
    python job_filler.py --config examples/sample_application.json --output ./out

The resulting Markdown and JSON manifest can be reviewed before copying the
answers into an applicant tracking system (ATS).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional


class SafeFormatDict(dict):
    """Dictionary that leaves unresolved keys untouched during formatting."""

    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return "{" + key + "}"


def load_structured_file(path: Path) -> Dict[str, Any]:
    """Load a configuration file in JSON or YAML format.

    Parameters
    ----------
    path:
        The file to load.

    Returns
    -------
    dict
        Parsed configuration data.
    """

    suffix = path.suffix.lower()
    with path.open("r", encoding="utf-8") as stream:
        if suffix == ".json":
            return json.load(stream)

        if suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except ImportError as exc:  # pragma: no cover - informative
                raise RuntimeError(
                    "PyYAML is required to load YAML configurations. "
                    "Install it with `pip install pyyaml` or use JSON instead."
                ) from exc

            return yaml.safe_load(stream)

    raise ValueError(
        f"Unsupported configuration format '{suffix}'. "
        "Expected .json, .yaml, or .yml"
    )


def slugify(value: str) -> str:
    """Return a filesystem-safe slug for *value*."""

    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-") or "application"


def _format_template(template: str, context: Mapping[str, Any]) -> str:
    """Render *template* using ``str.format`` semantics with safe defaults."""

    return template.format_map(SafeFormatDict(context))


@dataclass
class CandidateProfile:
    """Structured information about the applicant."""

    full_name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: Optional[str] = None
    resume: Optional[str] = None
    additional: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation for templating."""

        data = asdict(self)
        # Flatten optional fields to avoid nested structures in templates.
        data.update(self.additional)
        return data


@dataclass
class JobPosting:
    """Data describing the job opening."""

    title: str
    company: str
    location: Optional[str] = None
    apply_url: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApplicationQuestion:
    """A single application question and its generated answer."""

    prompt: str
    answer: str


@dataclass
class Attachment:
    """Metadata about a supporting document for the application."""

    label: str
    path: str
    exists: bool


@dataclass
class JobApplication:
    """Container for the generated job application."""

    candidate: CandidateProfile
    job: JobPosting
    questions: List[ApplicationQuestion]
    attachments: List[Attachment]
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def slug(self) -> str:
        return slugify(f"{self.candidate.full_name}-{self.job.title}-{self.job.company}")

    def render_markdown(self) -> str:
        """Create a Markdown document summarizing the application."""

        lines: List[str] = []
        lines.append(f"# Application for {self.job.title} at {self.job.company}")
        lines.append("")
        lines.append("## Candidate")
        lines.append(f"- **Name:** {self.candidate.full_name}")
        lines.append(f"- **Email:** {self.candidate.email}")
        if self.candidate.phone:
            lines.append(f"- **Phone:** {self.candidate.phone}")
        if self.candidate.address:
            lines.append(f"- **Address:** {self.candidate.address}")
        if self.candidate.linkedin:
            lines.append(f"- **LinkedIn:** {self.candidate.linkedin}")
        if self.candidate.portfolio:
            lines.append(f"- **Portfolio:** {self.candidate.portfolio}")

        lines.append("")
        lines.append("## Job Details")
        lines.append(f"- **Title:** {self.job.title}")
        lines.append(f"- **Company:** {self.job.company}")
        if self.job.location:
            lines.append(f"- **Location:** {self.job.location}")
        if self.job.apply_url:
            lines.append(f"- **Apply URL:** {self.job.apply_url}")
        if self.job.keywords:
            keyword_text = ", ".join(self.job.keywords)
            lines.append(f"- **Keywords:** {keyword_text}")
        if self.job.description:
            lines.append("")
            lines.append("### Description Snippet")
            lines.append(self.job.description)

        lines.append("")
        lines.append("## Tailored Responses")
        for idx, question in enumerate(self.questions, start=1):
            lines.append(f"### Question {idx}")
            lines.append(question.prompt)
            lines.append("")
            lines.append("**Answer**")
            lines.append(question.answer)
            lines.append("")

        if not self.questions:
            lines.append("(No custom questions provided.)")
            lines.append("")

        lines.append("## Attachments")
        if self.attachments:
            for attachment in self.attachments:
                status = "✅" if attachment.exists else "⚠️ missing"
                lines.append(f"- {status} {attachment.label}: {attachment.path}")
        else:
            lines.append("(No attachments configured.)")

        lines.append("")
        lines.append(
            f"_Generated on {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}_"
        )

        return "\n".join(lines).strip() + "\n"

    def manifest(self) -> Dict[str, Any]:
        """Return structured data describing the generated application."""

        return {
            "candidate": self.candidate.to_dict(),
            "job": self.job.to_dict(),
            "questions": [asdict(q) for q in self.questions],
            "attachments": [asdict(att) for att in self.attachments],
            "generated_at": self.generated_at.isoformat() + "Z",
        }


class ApplicationBuilder:
    """Factory for constructing :class:`JobApplication` from dictionaries."""

    def __init__(self, data: Mapping[str, Any]):
        self.data = data

    def build(self) -> JobApplication:
        extra_context = dict(self.data.get("variables", {}))
        extra_context.setdefault("project_root", str(Path(__file__).resolve().parent))
        base_context = SafeFormatDict(extra_context)

        candidate = self._build_candidate(self.data.get("candidate", {}), base_context)
        job = self._build_job(self.data.get("job", {}), base_context)

        context = SafeFormatDict({
            "candidate": candidate.to_dict(),
            "job": job.to_dict(),
            **extra_context,
        })

        questions = self._build_questions(self.data.get("application", {}).get("questions", []), context)
        attachments = self._build_attachments(
            self.data.get("application", {}).get("attachments", []),
            context,
        )

        return JobApplication(candidate=candidate, job=job, questions=questions, attachments=attachments)

    def _build_candidate(
        self,
        data: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> CandidateProfile:
        if "full_name" not in data or "email" not in data:
            raise ValueError("Candidate information must include 'full_name' and 'email'.")

        resolved = self._format_structure(data, context)

        known_fields = {
            key: data.get(key)
            for key in [
                "full_name",
                "email",
                "phone",
                "address",
                "linkedin",
                "portfolio",
                "resume",
            ]
        }

        known_fields = {
            key: resolved.get(key)
            for key in [
                "full_name",
                "email",
                "phone",
                "address",
                "linkedin",
                "portfolio",
                "resume",
            ]
        }

        additional = {
            key: value
            for key, value in resolved.items()
            if key not in known_fields
        }

        return CandidateProfile(**known_fields, additional=additional)  # type: ignore[arg-type]

    def _build_job(
        self,
        data: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> JobPosting:
        if "title" not in data or "company" not in data:
            raise ValueError("Job information must include 'title' and 'company'.")

        resolved = self._format_structure(data, context)

        return JobPosting(
            title=resolved.get("title"),
            company=resolved.get("company"),
            location=resolved.get("location"),
            apply_url=resolved.get("apply_url"),
            keywords=list(resolved.get("keywords", []) or []),
            description=resolved.get("description"),
        )

    def _build_questions(
        self,
        data: Iterable[Mapping[str, Any]],
        context: Mapping[str, Any],
    ) -> List[ApplicationQuestion]:
        questions: List[ApplicationQuestion] = []
        for entry in data:
            prompt = entry.get("prompt")
            if not prompt:
                raise ValueError("Each question entry must include a 'prompt'.")

            answer = entry.get("answer")
            template = entry.get("answer_template")

            if answer and template:
                raise ValueError(
                    "Question entry should provide only 'answer' or 'answer_template', not both."
                )

            if template:
                answer = _format_template(template, context)
            elif answer is None:
                raise ValueError(
                    "Question entry must include either 'answer' or 'answer_template'."
                )

            questions.append(ApplicationQuestion(prompt=prompt, answer=answer))

        return questions

    def _build_attachments(
        self,
        data: Iterable[Mapping[str, Any]],
        context: Mapping[str, Any],
    ) -> List[Attachment]:
        attachments: List[Attachment] = []
        for entry in data:
            label = entry.get("label")
            path_template = entry.get("path")
            if not label or not path_template:
                raise ValueError(
                    "Attachment entries must include both 'label' and 'path'."
                )

            resolved_path = _format_template(path_template, context)
            path_obj = Path(resolved_path).expanduser()
            attachments.append(
                Attachment(label=label, path=str(path_obj), exists=path_obj.exists())
            )

        return attachments

    def _format_structure(self, value: Any, context: Mapping[str, Any]) -> Any:
        if isinstance(value, str):
            return _format_template(value, context)
        if isinstance(value, Mapping):
            return {key: self._format_structure(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [self._format_structure(item, context) for item in value]
        return value


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to the JSON or YAML configuration file describing the application.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./generated_applications"),
        help="Directory where the generated files will be written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated Markdown instead of writing files.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)

    if not args.config.exists():
        raise SystemExit(f"Configuration file '{args.config}' does not exist.")

    config = load_structured_file(args.config)

    builder = ApplicationBuilder(config)
    application = builder.build()

    markdown = application.render_markdown()

    if args.dry_run:
        print(markdown)
        return 0

    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = application.slug()
    markdown_path = output_dir / f"{slug}.md"
    manifest_path = output_dir / f"{slug}.json"

    markdown_path.write_text(markdown, encoding="utf-8")
    manifest_path.write_text(json.dumps(application.manifest(), indent=2), encoding="utf-8")

    print(f"Generated Markdown: {markdown_path}")
    print(f"Generated manifest: {manifest_path}")

    missing = [att for att in application.attachments if not att.exists]
    if missing:
        print("Warning: Some attachments are missing:")
        for attachment in missing:
            print(f"  - {attachment.label}: {attachment.path}")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
