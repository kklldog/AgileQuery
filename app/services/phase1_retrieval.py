import sqlite3

from app.domain.errors import QueryValidationError
from app.domain.models import JoinRuleMeta, MetricRuleMeta, RetrievedContext, SpaceMeta, TableMeta
from app.repositories.catalog import InMemoryCatalogRepository


class RetrievalService:
    def __init__(self, catalog: InMemoryCatalogRepository) -> None:
        self._catalog = catalog
        try:
            self._fts_connection = sqlite3.connect(":memory:")
            self._initialize_fts_schema()
        except sqlite3.OperationalError as exc:
            raise RuntimeError("SQLite FTS5 is required for RetrievalService") from exc

    def _initialize_fts_schema(self) -> None:
        self._fts_connection.execute(
            "CREATE VIRTUAL TABLE knowledge_docs USING fts5(database_id, space_id, doc_type, doc_id, table_name, content)"
        )
        for database_id in self._catalog.database_ids():
            for space in self._catalog.list_spaces(database_id):
                for table in self._catalog.list_tables(database_id, space.id):
                    content = self._build_table_document(space, table)
                    self._fts_connection.execute(
                        "INSERT INTO knowledge_docs (database_id, space_id, doc_type, doc_id, table_name, content) VALUES (?, ?, ?, ?, ?, ?)",
                        (database_id, space.id, "table", table.name, table.name, content),
                    )
                for metric_rule in self._catalog.list_metric_rules(database_id, space.id):
                    content = self._build_metric_rule_document(space, metric_rule)
                    self._fts_connection.execute(
                        "INSERT INTO knowledge_docs (database_id, space_id, doc_type, doc_id, table_name, content) VALUES (?, ?, ?, ?, ?, ?)",
                        (database_id, space.id, "metric_rule", metric_rule.id, metric_rule.source_table, content),
                    )
        self._fts_connection.commit()

    def retrieve(self, database_id: str, question: str, space_id: str | None = None) -> RetrievedContext:
        database = self._catalog.get_database(database_id)
        resolved_space, routing_diagnostics = self._resolve_space(database_id, question, space_id)
        strong_terms, fallback_terms = self._extract_keywords(question)
        strong_terms, fallback_terms = self._filter_resolved_space_terms(strong_terms, fallback_terms, resolved_space)
        tables, metric_rules, retrieval_diagnostics = self._fts_retrieve_context(
            database_id,
            resolved_space.id,
            strong_terms,
            fallback_terms,
        )
        join_rules = self._catalog.list_join_rules(database_id, resolved_space.id)
        diagnostics = [
            f"routed_space={resolved_space.id}",
            f"keywords={','.join([*strong_terms, *fallback_terms])}",
            f"context_join_rules={','.join([join_rule.id for join_rule in join_rules])}",
            *routing_diagnostics,
            *retrieval_diagnostics,
        ]
        return RetrievedContext(
            database=database,
            space=resolved_space,
            tables=tables,
            keywords=[*strong_terms, *fallback_terms],
            join_rules=join_rules,
            metric_rules=metric_rules,
            diagnostics=diagnostics,
        )

    def _resolve_space(self, database_id: str, question: str, space_id: str | None) -> tuple[SpaceMeta, list[str]]:
        if space_id:
            return self._catalog.get_space(database_id, space_id), ["routing_strategy=explicit"]

        spaces = self._catalog.list_spaces(database_id)
        if len(spaces) == 1:
            return spaces[0], ["routing_strategy=single_space_default"]

        question_terms = set(self._document_terms(question))
        scored_spaces: list[tuple[SpaceMeta, int]] = []
        for space in spaces:
            space_terms = set(
                self._document_terms(
                    " ".join([space.id, space.name, space.description, *space.sample_questions])
                )
            )
            score = len(question_terms & space_terms)
            scored_spaces.append((space, score))

        scored_spaces.sort(key=lambda item: item[1], reverse=True)
        top_space, top_score = scored_spaces[0]
        second_score = scored_spaces[1][1] if len(scored_spaces) > 1 else -1
        score_details = ",".join([f"{space.id}:{score}" for space, score in scored_spaces])

        if top_score <= 0 or top_score == second_score:
            raise QueryValidationError("Unable to resolve target space from the question")

        return top_space, [f"routing_strategy=scored", f"routing_scores={score_details}"]

    def _extract_keywords(self, question: str) -> tuple[list[str], list[str]]:
        normalized = question.replace("?", " ").replace("？", " ").strip()
        words = [token for token in normalized.split() if token]
        compact = normalized.replace(" ", "")
        bigrams = [compact[index : index + 2] for index in range(max(len(compact) - 1, 0))]
        strong_terms = self._unique_terms([*words, compact])[:6]
        fallback_terms = self._unique_terms(bigrams)[:8]
        return strong_terms, fallback_terms

    def _fts_retrieve_context(
        self,
        database_id: str,
        space_id: str,
        strong_terms: list[str],
        fallback_terms: list[str],
    ) -> tuple[list[TableMeta], list[MetricRuleMeta], list[str]]:
        diagnostics: list[str] = []

        if strong_terms:
            strong_expression = " AND ".join([self._quote_match_term(keyword) for keyword in strong_terms])
            strong_matches = self._query_document_matches(database_id, space_id, strong_expression)
            if strong_matches:
                tables, metric_rules = self._resolve_document_matches(
                    database_id,
                    space_id,
                    strong_matches,
                    [*strong_terms, *fallback_terms],
                )
                diagnostics.extend(
                    [
                        "match_strategy=strong_and",
                        f"match_expression={strong_expression}",
                        f"matched_tables={','.join([table.name for table in tables])}",
                        f"matched_metric_rules={','.join([metric_rule.id for metric_rule in metric_rules])}",
                        f"retrieved_tables={len(tables)}",
                    ]
                )
                return tables, metric_rules, diagnostics

        if fallback_terms:
            fallback_expression = " OR ".join([self._quote_match_term(keyword) for keyword in fallback_terms])
            fallback_matches = self._query_document_matches(database_id, space_id, fallback_expression)
            if fallback_matches:
                tables, metric_rules = self._resolve_document_matches(
                    database_id,
                    space_id,
                    fallback_matches,
                    [*strong_terms, *fallback_terms],
                )
                diagnostics.extend(
                    [
                        "match_strategy=fallback_or",
                        f"match_expression={fallback_expression}",
                        f"matched_tables={','.join([table.name for table in tables])}",
                        f"matched_metric_rules={','.join([metric_rule.id for metric_rule in metric_rules])}",
                        f"retrieved_tables={len(tables)}",
                    ]
                )
                return tables, metric_rules, diagnostics

        raise QueryValidationError("No relevant tables matched the question in the resolved space")

    def _query_document_matches(self, database_id: str, space_id: str, match_expression: str) -> list[tuple[str, str, str]]:
        cursor = self._fts_connection.execute(
            """
            SELECT doc_type, doc_id, table_name
            FROM knowledge_docs
            WHERE database_id = ? AND space_id = ? AND knowledge_docs MATCH ?
            ORDER BY bm25(knowledge_docs)
            LIMIT 5
            """,
            (database_id, space_id, match_expression),
        )
        return [(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def _resolve_document_matches(
        self,
        database_id: str,
        space_id: str,
        matches: list[tuple[str, str, str]],
        keywords: list[str],
    ) -> tuple[list[TableMeta], list[MetricRuleMeta]]:
        all_tables = self._catalog.list_tables(database_id, space_id)
        table_lookup = {table.name: table for table in all_tables}
        metric_rule_lookup = {metric_rule.id: metric_rule for metric_rule in self._catalog.list_metric_rules(database_id, space_id)}
        table_names: list[str] = []
        metric_rule_ids: list[str] = []

        for doc_type, doc_id, table_name in matches:
            if table_name not in table_names:
                table_names.append(table_name)
            if doc_type == "metric_rule" and doc_id not in metric_rule_ids:
                metric_rule_ids.append(doc_id)

        tables = [table_lookup[name] for name in table_names if name in table_lookup]
        metric_rules = [metric_rule_lookup[metric_rule_id] for metric_rule_id in metric_rule_ids if metric_rule_id in metric_rule_lookup]
        metric_rules = self._augment_metric_rules(metric_rule_lookup, metric_rules, table_names, keywords)
        return tables, metric_rules

    def _augment_metric_rules(
        self,
        metric_rule_lookup: dict[str, MetricRuleMeta],
        metric_rules: list[MetricRuleMeta],
        table_names: list[str],
        keywords: list[str],
    ) -> list[MetricRuleMeta]:
        rule_ids = {metric_rule.id for metric_rule in metric_rules}
        for metric_rule in metric_rule_lookup.values():
            if metric_rule.id in rule_ids:
                continue
            if metric_rule.source_table not in table_names:
                continue
            searchable_text = " ".join([metric_rule.name, metric_rule.description, *metric_rule.synonyms])
            if self._has_keyword_overlap(searchable_text, keywords):
                metric_rules.append(metric_rule)
                rule_ids.add(metric_rule.id)
        return metric_rules

    def _build_table_document(self, space: SpaceMeta, table: TableMeta) -> str:
        important_terms = [space.name, space.description, *space.sample_questions, table.alias, table.name, table.business_name]
        column_terms = [column.name for column in table.columns] + [column.description for column in table.columns]
        text = " ".join([*important_terms, table.business_name, table.name, *column_terms])
        emitted_terms = self._document_terms(text)
        return " ".join(emitted_terms)

    def _build_metric_rule_document(self, space: SpaceMeta, metric_rule: MetricRuleMeta) -> str:
        text = " ".join(
            [
                space.name,
                space.description,
                metric_rule.id,
                metric_rule.name,
                metric_rule.description,
                metric_rule.expression,
                metric_rule.source_table,
                metric_rule.output_alias,
                *metric_rule.synonyms,
            ]
        )
        return " ".join(self._document_terms(text))

    def _document_terms(self, text: str) -> list[str]:
        normalized = text.replace("?", " ").replace("？", " ").replace("，", " ").replace("。", " ").strip()
        words = [token for token in normalized.split() if token]
        compact = normalized.replace(" ", "")
        bigrams = [compact[index : index + 2] for index in range(max(len(compact) - 1, 0))]
        return self._unique_terms([*words, compact, *bigrams])

    def _filter_resolved_space_terms(
        self,
        strong_terms: list[str],
        fallback_terms: list[str],
        space: SpaceMeta,
    ) -> tuple[list[str], list[str]]:
        space_markers = [space.id.lower(), space.name.lower()]

        def is_space_only_term(term: str) -> bool:
            lowered = term.lower()
            return any(lowered in marker or marker in lowered for marker in space_markers if marker)

        return (
            [term for term in strong_terms if not is_space_only_term(term)],
            [term for term in fallback_terms if not is_space_only_term(term)],
        )

    def _has_keyword_overlap(self, text: str, keywords: list[str]) -> bool:
        text_terms = set(self._document_terms(text))
        return any(keyword in text_terms for keyword in keywords)

    def _unique_terms(self, terms: list[str]) -> list[str]:
        ordered_terms: list[str] = []
        for term in terms:
            if term and term not in ordered_terms:
                ordered_terms.append(term)
        return ordered_terms

    def _quote_match_term(self, term: str) -> str:
        escaped = term.replace('"', '""')
        return f'"{escaped}"'
