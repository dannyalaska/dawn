from __future__ import annotations

import json
from typing import Annotated, Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RenameStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["rename"]
    column: str
    new_name: str


class CastStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["cast"]
    column: str
    dtype: str


class TrimStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["trim"]
    column: str
    method: Literal["both", "left", "right"] = "both"


class ParseDateStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["parse_date"]
    column: str
    format: str | None = None
    errors: Literal["raise", "coerce", "ignore"] = "coerce"


class FillNAStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["fillna"]
    column: str
    value: Any


class MapValuesStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["map_values"]
    column: str
    mapping: dict[str, Any]
    default: Any | None = None


class SplitColumnStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["split_column"]
    column: str
    into: list[str]
    delimiter: str
    drop_original: bool = False

    @field_validator("into")
    def _at_least_two(cls, v: list[str]):  # noqa: N805
        if len(v) < 2:
            raise ValueError("split_column into must have at least two target columns")
        return v


class MergeColumnsStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["merge_columns"]
    columns: list[str]
    into: str
    separator: str = " "
    drop_sources: bool = False

    @field_validator("columns")
    def _columns_required(cls, v: list[str]):  # noqa: N805
        if len(v) < 2:
            raise ValueError("merge_columns requires at least two source columns")
        return v


class DeduplicateStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["deduplicate"]
    subset: list[str]
    keep: Literal["first", "last", "any"] = "first"

    @field_validator("subset")
    def _subset_non_empty(cls, v: list[str]):  # noqa: N805
        if not v:
            raise ValueError("deduplicate subset cannot be empty")
        return v


class JoinStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["join"]
    right_dataset: str
    left_on: list[str]
    right_on: list[str]
    how: Literal["left", "inner", "right", "outer"] = "left"
    suffixes: tuple[str, str] = ("", "_right")
    select: list[str] | None = None

    @field_validator("left_on", "right_on")
    def _non_empty(cls, v: list[str]):  # noqa: N805
        if not v:
            raise ValueError("join keys cannot be empty")
        return v

    @field_validator("suffixes")
    def _suffix_len(cls, v: tuple[str, str]):  # noqa: N805
        if len(v) != 2:
            raise ValueError("suffixes must provide exactly two values")
        return v


TransformStep = Annotated[
    RenameStep
    | CastStep
    | TrimStep
    | ParseDateStep
    | FillNAStep
    | MapValuesStep
    | SplitColumnStep
    | MergeColumnsStep
    | DeduplicateStep
    | JoinStep,
    Field(discriminator="type"),
]


class TransformDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    feed_identifier: str
    target_table: str
    steps: list[TransformStep]
    description: str | None = None
    load_strategy: Literal["append", "replace"] = "append"
    generate_dbt_model: bool = False
    unique_key: list[str] | None = None
    incremental: bool = False


def _ensure_dataframe(sample_rows: list[dict[str, Any]], limit: int = 500) -> pd.DataFrame:
    if not sample_rows:
        raise ValueError("sample_rows must contain at least one row")
    rows = sample_rows[:limit]
    return pd.DataFrame(rows)


def apply_transform(
    df: pd.DataFrame,
    steps: list[TransformStep],
    *,
    context: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    context = context or {}
    out = df.copy()
    for step in steps:
        if isinstance(step, RenameStep):
            out = out.rename(columns={step.column: step.new_name})
        elif isinstance(step, CastStep):
            out[step.column] = out[step.column].astype(step.dtype)
        elif isinstance(step, TrimStep):
            series = out[step.column].astype(str)
            if step.method == "left":
                out[step.column] = series.str.lstrip()
            elif step.method == "right":
                out[step.column] = series.str.rstrip()
            else:
                out[step.column] = series.str.strip()
        elif isinstance(step, ParseDateStep):
            out[step.column] = pd.to_datetime(
                out[step.column], format=step.format, errors=step.errors
            )
        elif isinstance(step, FillNAStep):
            out[step.column] = out[step.column].fillna(step.value)
        elif isinstance(step, MapValuesStep):
            mapped = out[step.column].map(step.mapping)
            if step.default is not None:
                mapped = mapped.fillna(step.default)
            else:
                mapped = mapped.fillna(out[step.column])
            out[step.column] = mapped
        elif isinstance(step, SplitColumnStep):
            split_cols = out[step.column].astype(str).str.split(step.delimiter, expand=True)
            for idx, target in enumerate(step.into):
                out[target] = split_cols.iloc[:, idx] if idx < split_cols.shape[1] else None
            if step.drop_original and step.column in out.columns:
                out = out.drop(columns=[step.column])
        elif isinstance(step, MergeColumnsStep):
            merged = (
                out[step.columns]
                .fillna("")
                .astype(str)
                .agg(lambda row, _sep=step.separator: _sep.join(row), axis=1)
            )
            out[step.into] = merged
            if step.drop_sources:
                out = out.drop(columns=[c for c in step.columns if c in out.columns])
        elif isinstance(step, DeduplicateStep):
            keep_arg: str | bool = step.keep
            if step.keep == "any":
                keep_arg = False
            out = out.drop_duplicates(subset=step.subset, keep=keep_arg)
        elif isinstance(step, JoinStep):
            right_df = context.get(step.right_dataset)
            if right_df is None:
                raise ValueError(f"Join dataset '{step.right_dataset}' not provided in context")
            join_source = right_df.copy()
            if step.select:
                join_source = join_source[step.select]
            out = out.merge(
                join_source,
                left_on=step.left_on,
                right_on=step.right_on,
                how=step.how,
                suffixes=step.suffixes,
            )
        else:  # pragma: no cover
            raise ValueError(f"Unhandled transform step {step}")
    return out


def diff_frames(before: pd.DataFrame, after: pd.DataFrame) -> dict[str, Any]:
    before_cols = set(before.columns)
    after_cols = set(after.columns)
    common_cols = before_cols & after_cols
    type_changes: list[dict[str, Any]] = []
    for col in sorted(common_cols):
        if str(before[col].dtype) != str(after[col].dtype):
            type_changes.append(
                {
                    "column": col,
                    "before": str(before[col].dtype),
                    "after": str(after[col].dtype),
                }
            )
    return {
        "rows_before": int(len(before)),
        "rows_after": int(len(after)),
        "row_delta": int(len(after) - len(before)),
        "columns_added": sorted(after_cols - before_cols),
        "columns_removed": sorted(before_cols - after_cols),
        "type_changes": type_changes,
        "preview_before": before.head(5).to_dict(orient="records"),
        "preview_after": after.head(5).to_dict(orient="records"),
    }


def run_dry_run(
    *,
    sample_rows: list[dict[str, Any]],
    steps: list[TransformStep],
    context_samples: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    context_frames: dict[str, pd.DataFrame] = {}
    for key, rows in (context_samples or {}).items():
        context_frames[key] = pd.DataFrame(rows)

    base_df = _ensure_dataframe(sample_rows)
    transformed = apply_transform(base_df, steps, context=context_frames)
    return diff_frames(base_df, transformed)


def _step_label(step: TransformStep) -> str:
    if isinstance(step, RenameStep):
        return f"Rename {step.column} → {step.new_name}"
    if isinstance(step, CastStep):
        return f"Cast {step.column} to {step.dtype}"
    if isinstance(step, TrimStep):
        return f"Trim {step.method} on {step.column}"
    if isinstance(step, ParseDateStep):
        fmt = step.format or "auto"
        return f"Parse dates in {step.column} (format: {fmt})"
    if isinstance(step, FillNAStep):
        return f"Fill nulls in {step.column}"
    if isinstance(step, MapValuesStep):
        return f"Map values in {step.column}"
    if isinstance(step, SplitColumnStep):
        targets = ", ".join(step.into)
        return f"Split {step.column} → {targets}"
    if isinstance(step, MergeColumnsStep):
        sources = ", ".join(step.columns)
        return f"Merge {sources} → {step.into}"
    if isinstance(step, DeduplicateStep):
        subset = ", ".join(step.subset)
        return f"Deduplicate by {subset}"
    if isinstance(step, JoinStep):
        return f"{step.how.title()} join with {step.right_dataset}"
    return step.type


def generate_transform_docs(definition: TransformDefinition) -> dict[str, str]:
    markdown_lines = [
        f"# Transform {definition.name}",
        "",
        f"- Target table: `{definition.target_table}`",
        f"- Feed: `{definition.feed_identifier}`",
        f"- Load strategy: `{definition.load_strategy}`",
        "",
        "## Steps",
    ]
    for idx, step in enumerate(definition.steps, 1):
        markdown_lines.append(f"{idx}. {_step_label(step)}")

    mermaid_lines = ["graph TD", "    src[Source DataFrame]"]
    previous_node = "src"
    for idx, step in enumerate(definition.steps, 1):
        node = f"step{idx}"
        label = _step_label(step).replace("`", "")
        mermaid_lines.append(f"    {node}[{label}]")
        mermaid_lines.append(f"    {previous_node} --> {node}")
        previous_node = node
    mermaid_lines.append(f"    {previous_node} --> tgt[{definition.target_table}]")

    return {
        "markdown": "\n".join(markdown_lines),
        "mermaid": "\n".join(mermaid_lines),
    }


def generate_python_script(definition: TransformDefinition) -> str:
    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "import pandas as pd",
        "from sqlalchemy import create_engine",
        "",
        "",
        "def run_transform(df: pd.DataFrame, *, context: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:",
        "    context = context or {}",
        "    df = df.copy()",
    ]

    mapping_counter = 0
    temp_counter = 0

    for step in definition.steps:
        if isinstance(step, RenameStep):
            lines.append(f"    df = df.rename(columns={{'{step.column}': '{step.new_name}'}})")
        elif isinstance(step, CastStep):
            lines.append(f"    df['{step.column}'] = df['{step.column}'].astype('{step.dtype}')")
        elif isinstance(step, TrimStep):
            if step.method == "left":
                accessor = ".str.lstrip()"
            elif step.method == "right":
                accessor = ".str.rstrip()"
            else:
                accessor = ".str.strip()"
            lines.append(f"    df['{step.column}'] = df['{step.column}'].astype(str){accessor}")
        elif isinstance(step, ParseDateStep):
            fmt_repr = repr(step.format) if step.format else "None"
            lines.append(
                f"    df['{step.column}'] = pd.to_datetime(df['{step.column}'], format={fmt_repr}, errors='{step.errors}')"
            )
        elif isinstance(step, FillNAStep):
            lines.append(
                f"    df['{step.column}'] = df['{step.column}'].fillna({repr(step.value)})"
            )
        elif isinstance(step, MapValuesStep):
            mapping_counter += 1
            name = f"_mapping_{mapping_counter}"
            lines.append(f"    {name} = {json.dumps(step.mapping)}")
            lines.append(f"    df['{step.column}'] = df['{step.column}'].map({name})")
            if step.default is not None:
                lines.append(
                    f"    df['{step.column}'] = df['{step.column}'].fillna({repr(step.default)})"
                )
            else:
                lines.append(
                    f"    df['{step.column}'] = df['{step.column}'].fillna(df['{step.column}'])"
                )
        elif isinstance(step, SplitColumnStep):
            temp_counter += 1
            name = f"_split_{temp_counter}"
            lines.append(
                f"    {name} = df['{step.column}'].astype(str).str.split({repr(step.delimiter)}, expand=True)"
            )
            for idx, target in enumerate(step.into):
                lines.append(
                    f"    df['{target}'] = {name}.iloc[:, {idx}] if {name}.shape[1] > {idx} else None"
                )
            if step.drop_original:
                lines.append(f"    df = df.drop(columns=['{step.column}'])")
        elif isinstance(step, MergeColumnsStep):
            cols_repr = json.dumps(step.columns)
            lines.append(
                f"    df['{step.into}'] = df[{cols_repr}].fillna('').astype(str).agg(lambda row: '{step.separator}'.join(row), axis=1)"
            )
            if step.drop_sources:
                lines.append(f"    df = df.drop(columns={[c for c in step.columns]})")
        elif isinstance(step, DeduplicateStep):
            keep_arg = "False" if step.keep == "any" else repr(step.keep)
            lines.append(
                f"    df = df.drop_duplicates(subset={json.dumps(step.subset)}, keep={keep_arg})"
            )
        elif isinstance(step, JoinStep):
            lines.append(f"    right_df = context.get('{step.right_dataset}')")
            lines.append(
                f"    if right_df is None:\n        raise ValueError('Join dataset {step.right_dataset} missing in context')"
            )
            if step.select:
                lines.append(f"    right_df = right_df[{json.dumps(step.select)}]")
            suffixes_repr = step.suffixes
            lines.append(
                f"    df = df.merge(right_df, left_on={json.dumps(step.left_on)}, right_on={json.dumps(step.right_on)}, how='{step.how}', suffixes={suffixes_repr})"
            )
        else:  # pragma: no cover
            raise ValueError(f"Unhandled transform step {step}")

    lines.extend(
        [
            "    return df",
            "",
            "",
            "def load_into_sql(",
            "    df: pd.DataFrame, *, engine_url: str, table_name: str, if_exists: str = '"
            + definition.load_strategy
            + "'",
            ") -> None:",
            "    engine = create_engine(engine_url)",
            "    with engine.begin() as conn:",
            "        df.to_sql(table_name, conn, if_exists=if_exists, index=False)",
        ]
    )

    return "\n".join(lines)


def generate_dbt_model(definition: TransformDefinition) -> str | None:
    if not definition.generate_dbt_model:
        return None

    config_lines = ["{{ config("]
    materialized = "incremental" if definition.incremental else "table"
    config_lines.append(f"    materialized='{materialized}',")
    if definition.unique_key:
        config_lines.append(f"    unique_key={json.dumps(definition.unique_key)},")
    config_lines.append(") }}")

    body = [
        "\n".join(config_lines),
        "",
        f"-- Auto-generated stub for transform '{definition.name}'.",
        "-- Replace with an equivalent SQL definition if desired.",
        "WITH source AS (",
        f"    SELECT * FROM {{ ref('{definition.feed_identifier}_staging') }}",
        ")",
        "SELECT",
        "    *",
        "FROM source",
    ]
    return "\n".join(body)
