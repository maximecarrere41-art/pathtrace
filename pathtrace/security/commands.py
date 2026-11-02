import re


SHELL_SYNTAX = re.compile(
    r'''"(?:\\.|`.|[^"\\`])*"|'(?:''|[^'])*'|\\[;&|"'\\]|`.|&&|\|\||\|&|(?<![<>])&|[;|\r\n]'''
)
SEPARATORS = {"&&", "||", "|&", "&", ";", "|", "\r", "\n"}


def split_shell_commands(command: str) -> tuple[str, ...]:
    boundaries = [match.span() for match in SHELL_SYNTAX.finditer(command)
                  if match.group() in SEPARATORS]
    starts = [0, *(end for _, end in boundaries)]
    ends = [*(start for start, _ in boundaries), len(command)]
    return tuple(part for start, end in zip(starts, ends)
                 if (part := command[start:end].strip()))
