import re
import json
from dataclasses import dataclass


@dataclass
class Token:
    type: str
    value: str


TOKEN_RE = re.compile(
    r"""
    (?P<WS>\s+)                             # пробелы и переводы строк
  | (?P<DICT_START>@\{)                     # @{ начало словаря
  | (?P<LBRACE>\{)                          # {
  | (?P<RBRACE>\})                          # }
  | (?P<LPAREN>\()                          # (
  | (?P<RPAREN>\))                          # )
  | (?P<COMMA>,)                            # ,
  | (?P<EQUAL>=)                            # =
  | (?P<SEMICOLON>;)
  | (?P<ARRAY>\barray\b)                    # array
  | (?P<DEF>\bdef\b)                        # def
  | (?P<CONSTREF>\$[A-Za-z_][A-Za-z0-9_]*\$)# $name$
  | (?P<STRING>\[\[[^\]]*\]\])              # [[строка]]
  | (?P<NUMBER>0[bB][01]+)                  # двоичное число
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)       # идентификатор
    """,
    re.VERBOSE,
)


def tokenize(text: str):
    tokens = []
    pos = 0
    n = len(text)
    while pos < n:
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise SyntaxError(f"Неожиданный символ {text[pos]!r} на позиции {pos}")
        kind = m.lastgroup
        value = m.group(kind)
        pos = m.end()
        if kind == "WS":
            continue
        tokens.append(Token(kind, value))
    tokens.append(Token("EOF", ""))
    return tokens


def parse_binary(s: str) -> int:
    return int(s[2:], 2)


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.consts = {}

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def eat(self, expected_type: str):
        if self.current.type != expected_type:
            raise SyntaxError(
                f"Ожидался {expected_type}, а встретился {self.current.type} ({self.current.value})"
            )
        self.pos += 1

    def peek(self, offset=1) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def parse_program(self):
        while self.current.type == "LPAREN" and self.peek().type == "DEF":
            self.parse_const_def()
        value = self.parse_value()
        if self.current.type != "EOF":
            raise SyntaxError(f"Лишний текст после основного значения: {self.current}")
        return value

    def parse_const_def(self):
        self.eat("LPAREN")
        self.eat("DEF")
        if self.current.type != "IDENT":
            raise SyntaxError("Ожидалось имя константы после def")
        name = self.current.value
        self.eat("IDENT")
        value = self.parse_value()
        self.eat("RPAREN")
        self.eat("SEMICOLON")
        self.consts[name] = value

    def parse_value(self):
        tok = self.current

        if tok.type == "NUMBER":
            self.eat("NUMBER")
            return parse_binary(tok.value)

        if tok.type == "STRING":
            self.eat("STRING")
            return tok.value[2:-2]

        if tok.type == "CONSTREF":
            self.eat("CONSTREF")
            name = tok.value[1:-1]
            if name not in self.consts:
                raise SyntaxError(f"Неизвестная константа: {name}")
            return self.consts[name]

        if tok.type == "ARRAY":
            return self.parse_array()

        if tok.type == "DICT_START":
            return self.parse_dict()

        raise SyntaxError(f"Неожиданное значение: {tok.type} {tok.value}")

    def parse_array(self):
        items = []
        self.eat("ARRAY")
        self.eat("LPAREN")
        if self.current.type != "RPAREN":
            items.append(self.parse_value())
            while self.current.type == "COMMA":
                self.eat("COMMA")
                items.append(self.parse_value())
        self.eat("RPAREN")
        return items

    def parse_dict(self):
        result = {}
        self.eat("DICT_START")
        while self.current.type == "IDENT":
            key = self.current.value
            self.eat("IDENT")
            self.eat("EQUAL")
            value = self.parse_value()
            self.eat("SEMICOLON")
            result[key] = value
        self.eat("RBRACE")
        return result


def translate_text(text: str):
    tokens = tokenize(text)
    parser = Parser(tokens)
    data = parser.parse_program()
    return data


def translate_file(input_path: str):
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()
    return translate_text(text)


def run_tests():
    tests_passed = 0

    def check(name, text, expected):
        nonlocal tests_passed
        result = translate_text(text)
        assert result == expected, f"{name} провален: ожидалось {expected}, получили {result}"
        tests_passed += 1

    # 1. Простой словарь без констант
    cfg1 = """
    @{
      port = 0b111111011000;
      host = [[localhost]];
    }
    """
    expected1 = {
        "port": int("111111011000", 2),
        "host": "localhost",
    }
    check("basic_dict", cfg1, expected1)

    # 2. Массив и вложенный словарь
    cfg2 = """
    @{
      numbers = array(0b1, 0b10, 0b11);
      nested  = @{
        name = [[inner]];
      };
    }
    """
    expected2 = {
        "numbers": [1, 2, 3],
        "nested": {"name": "inner"},
    }
    check("arrays_and_nested_dict", cfg2, expected2)

    # 3. Константы и использование $name$
    cfg3 = """
    (def base_port 0b111111011000);
    (def host_name [[localhost]]);

    @{
      port = $base_port$;
      host = $host_name$;
    }
    """
    expected3 = {
        "port": int("111111011000", 2),
        "host": "localhost",
    }
    check("consts", cfg3, expected3)

    # 4. Два примера из разных предметных областей
    cfg4 = """
    (def default_port 0b1010001011);
    (def base_hp 0b1100100);

    @{
      network = @{
        name = [[main_server]];
        port = $default_port$;
        tags = array([[web]], [[prod]]);
      };
      game = @{
        player = [[Hero]];
        hp = $base_hp$;
      };
    }
    """
    expected4 = {
        "network": {
            "name": "main_server",
            "port": int("1010001011", 2),
            "tags": ["web", "prod"],
        },
        "game": {
            "player": "Hero",
            "hp": int("1100100", 2),
        },
    }
    check("two_domains", cfg4, expected4)

    print(f"Все тесты пройдены: {tests_passed}")


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Транслятор учебного конфигурационного языка (вариант 15) в JSON"
    )
    parser.add_argument("-i", "--input", help="входной файл с конфигурацией")
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="запустить встроенные тесты и выйти",
    )

    args = parser.parse_args()

    if args.run_tests:
        run_tests()
        return

    if not args.input:
        parser.error("нужно указать -i или использовать --run-tests")

    try:
        data = translate_file(args.input)
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        print(json_str)
    except (SyntaxError, ValueError) as e:
        print("Синтаксическая ошибка:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
