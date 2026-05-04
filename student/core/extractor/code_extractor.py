import re
import json

class CodeExtractor:

    @classmethod
    def extract(cls, llm_response: str) -> str | None:
        extractors = [
            cls._extract_python_block,
            cls._extract_xml_tool_call,
            cls._extract_json_tool_call,
            cls._extract_react_format,
        ]
        for extractor in extractors:
            result = extractor(llm_response)
            if result:
                return result
        return None

    @staticmethod
    def _extract_python_block(text: str) -> str | None:
        pattern = r"```python\n(.*?)```"
        res = re.search(pattern, text, re.DOTALL)
        if res:
            return res.group(1).strip()
        return None

    @staticmethod
    def _extract_xml_tool_call(text: str) -> str | None:
        pass

    @staticmethod
    def _extract_json_tool_call(text: str) -> str | None:
        pass

    @staticmethod
    def _extract_react_format(text: str) -> str | None:
        pass