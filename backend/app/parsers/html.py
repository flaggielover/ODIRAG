from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from app.parsers.base import ParsedArtifact, ParsedSection, ParsedTable, table_to_markdown


class HtmlParser:
    def parse(self, content: bytes, *, filename: str | None = None) -> ParsedArtifact:
        del filename
        soup = BeautifulSoup(content, "lxml")
        for element in soup.select("script, style, noscript, nav, footer, header, form, aside"):
            element.decompose()
        root = soup.select_one("article, main, #UCAP-CONTENT, .pages_content") or soup.body or soup
        sections: list[ParsedSection] = []
        tables: list[ParsedTable] = []
        text_parts: list[str] = []
        links: list[dict[str, str]] = []
        current_title: str | None = None
        current_level = 0
        current_parts: list[str] = []
        for link in root.select("a[href]"):
            if isinstance(link, Tag):
                links.append({"text": link.get_text(" ", strip=True), "href": str(link["href"])})
        for element in root.select("h1, h2, h3, h4, h5, h6, p, li, table"):
            if not isinstance(element, Tag):
                continue
            if element.name and element.name.startswith("h"):
                if current_title is not None or current_parts:
                    sections.append(
                        ParsedSection(
                            current_title, current_level, "\n".join(current_parts).strip()
                        )
                    )
                current_title = element.get_text(" ", strip=True)
                current_level = int(element.name[1])
                current_parts = []
                text_parts.append("#" * current_level + " " + current_title)
            elif element.name == "table":
                table = _parse_table(element)
                if table.markdown:
                    tables.append(table)
                    current_parts.append(table.markdown)
                    text_parts.append(table.markdown)
            elif element.find_parent("table") is None:
                value = element.get_text(" ", strip=True)
                if value:
                    if element.name == "li":
                        value = f"- {value}"
                    current_parts.append(value)
                    text_parts.append(value)
        if current_title is not None or current_parts:
            sections.append(
                ParsedSection(current_title, current_level, "\n".join(current_parts).strip())
            )
        return ParsedArtifact(
            text="\n\n".join(text_parts),
            sections=tuple(sections),
            tables=tuple(tables),
            metadata={"links": links},
        )


def _parse_table(table: Tag) -> ParsedTable:
    rows = []
    for row in table.select("tr"):
        rows.append([cell.get_text(" ", strip=True) for cell in row.select("th, td")])
    if not rows:
        return ParsedTable((), (), "")
    first_has_header = bool(table.select_one("tr th"))
    headers = (
        rows[0] if first_has_header else [f"column_{index + 1}" for index in range(len(rows[0]))]
    )
    body = rows[1:] if first_has_header else rows
    return ParsedTable(
        tuple(headers),
        tuple(tuple(value for value in row) for row in body),
        table_to_markdown(headers, body),
    )
