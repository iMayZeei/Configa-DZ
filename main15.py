import json
import argparse
import sys

from lark import Lark, Transformer, v_args
from lark.exceptions import LarkError


GRAMMAR = r"""
    ?start: const_def* value

    const_def: "(" "def" IDENT value ")" ";"

    ?value: number
          | string
          | array
          | dict
          | const_ref

    number: BINARY
    string: STRING
    const_ref: CONSTREF

    array: "array" "(" [value ("," value)*] ")"

    dict: "@{" pair* "}"
    pair: IDENT "=" value ";"

    IDENT: /[A-Za-z_][A-Za-z0-9_]*/
    BINARY: /0[bB][01]+/
    STRING: /\[\[[^\]]*\]\]/
    CONSTREF: /\$[A-Za-z_][A-Za-z0-9_]*\$/

    %import common.WS
    %ignore WS
"""


@v_args(inline=True)
class ConfigTransformer(Transformer):
    def __init__(self):
        super().__init__()
        self.consts = {}

    def number(self, token):
        s = str(token)
        return int(s[2:], 2)

    def string(self, token):
        s = str(token)
        return s[2:-2]

    def const_def(self, name, value):
        self.consts[str(name)] = value
        return None

    def const_ref(self, token):
        name = str(token)[1:-1]
        if name not in self.consts:
            raise ValueError(f"Неизвестная константа: {name}")
        return self.consts[name]

    def pair(self, name, value):
        return str(name), value

    def dict(self, *pairs):
        result = {}
        for k, v in pairs:
            result[k] = v
        return result

    def array(self, *values):
        return list(values)

    def start(self, *items):
        for item in reversed(items):
            if item is not None:
                return item
        return None


parser = Lark(GRAMMAR, parser="lalr", start="start")


def translate_text(text: str):
    tree = parser.parse(text)
    transformer = ConfigTransformer()
    return transformer.transform(tree)


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
    parser_cli = argparse.ArgumentParser(
        description="Транслятор учебного конфигурационного языка (вариант 15, Lark) в JSON"
    )
    parser_cli.add_argument("-i", "--input", help="входной файл с конфигурацией")
    parser_cli.add_argument(
        "--run-tests",
        action="store_true",
        help="запустить встроенные тесты и выйти",
    )

    args = parser_cli.parse_args()

    if args.run_tests:
        run_tests()
        return

    if not args.input:
        parser_cli.error("нужно указать -i или использовать --run-tests")

    try:
        data = translate_file(args.input)
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        print(json_str)
    except (LarkError, ValueError) as e:
        print("Синтаксическая ошибка:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
