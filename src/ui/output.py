from prompt_toolkit import print_formatted_text
from prompt_toolkit.application import get_app_session
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style

from src.core.events import UIEventLevel


MSG_LEVEL_SYMBOL = {
    0: "[*] ",
    1: "[!] ",
    2: "[x] ",
    3: "[+] ",
    4: "[-] ",
    5: "[@] "
}

MSG_LEVEL_SYMBOL_STYLE = {
    0: "fg:green",
    1: "fg:yellow",
    2: "fg:red",
    3: "fg:blue",
    4: "fg:white",
    5: "fg:pink"
}


def proxy_print(text="", text_type=UIEventLevel.TEXT):
    session = get_app_session()
    if text_type == UIEventLevel.TEXT:
        print_formatted_text(text, output=session.output)
        return
    formatted_text = FormattedText([
        ('class:level', MSG_LEVEL_SYMBOL[text_type.value]),
        ('class:text', text)
    ])
    style = Style.from_dict({
        'level': MSG_LEVEL_SYMBOL_STYLE[text_type.value]
    })
    print_formatted_text(formatted_text, style=style, output=session.output)

