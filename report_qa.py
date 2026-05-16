import argparse
import json
import re
from pathlib import Path


FORBIDDEN_ANYWHERE = [
    "데일리메일",
    "Daily Mail",
    "생활법률",
    "상담소",
    "사연자",
    "동일 사안 1.00",
]

SUSPICIOUS_SELECTED = [
    "선거사무소",
    "개소식",
    "출정식",
    "사법쿠데타",
    "조작기소",
    "하야",
    "집회",
    "원내대표",
]

POLITE_ENDINGS = [
    "습니다",
    "입니다",
    "했습니다",
    "합니다",
    "겁니다",
    "이었습니다",
    "였습니다",
]

AWKWARD_FRAGMENTS = [
    "지만.",
]


def parse_args():
    parser = argparse.ArgumentParser(description="QA a generated morning report Markdown file.")
    parser.add_argument("report_path", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--min-selected", type=int, default=1)
    parser.add_argument("--max-selected", type=int, default=30)
    parser.add_argument("--fail-on-error", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    result = qa_report(args.report_path, args.min_selected, args.max_selected)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(output + "\n", encoding="utf-8")
    if args.fail_on_error and result["errors"]:
        raise SystemExit(1)


def qa_report(path, min_selected=1, max_selected=30):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    selected_blocks = extract_selected_blocks(text)
    errors = []
    warnings = []

    if "[보고 기사]" not in text:
        errors.append("missing report section header")
    if "[보류/제외 기사]" in text and text.index("[보류/제외 기사]") < text.index("[보고 기사]"):
        errors.append("hold section appears before report section")

    selected_count = len(selected_blocks)
    if selected_count < min_selected:
        warnings.append(f"selected item count below expected range: {selected_count}")
    if selected_count > max_selected:
        warnings.append(f"selected item count above expected range: {selected_count}")

    for term in FORBIDDEN_ANYWHERE:
        if term in text:
            errors.append(f"forbidden term found: {term}")

    for index, block in enumerate(selected_blocks, start=1):
        headline = block[0] if block else ""
        body = "\n".join(block)
        if not any(line.startswith("-") for line in block):
            errors.append(f"selected block {index} missing summary line: {headline}")
        if not any(line.startswith("http") for line in block):
            errors.append(f"selected block {index} missing URL: {headline}")
        for term in SUSPICIOUS_SELECTED:
            if term in body:
                warnings.append(f"suspicious selected term '{term}' in block {index}: {headline}")
        for term in POLITE_ENDINGS:
            if term in body:
                warnings.append(f"polite ending '{term}' in block {index}: {headline}")
        for term in AWKWARD_FRAGMENTS:
            if term in body:
                warnings.append(f"awkward fragment '{term}' in block {index}: {headline}")

    return {
        "report_path": str(path),
        "characters": len(text),
        "selected_count": selected_count,
        "section_count": sum(1 for line in lines if line.startswith("## ")),
        "errors": errors,
        "warnings": warnings,
        "status": "fail" if errors else ("warn" if warnings else "pass"),
    }


def extract_selected_blocks(text):
    report_part = text
    if "[보류/제외 기사]" in report_part:
        report_part = report_part.split("[보류/제외 기사]", 1)[0]
    blocks = []
    current = []
    for line in report_part.splitlines():
        if line.startswith("※"):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            if not line.strip():
                blocks.append(current)
                current = []
            else:
                current.append(line)
    if current:
        blocks.append(current)
    return blocks


if __name__ == "__main__":
    main()
