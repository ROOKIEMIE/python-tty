import shlex


def tokenize_cmd(cmd: str):
    cmd = cmd.strip()
    if cmd == "":
        return []
    try:
        return shlex.split(cmd, posix=True)
    except ValueError as exc:
        raise ValueError("Invalid command arguments") from exc


def get_command_token(cmd: str):
    tokens = tokenize_cmd(cmd)
    return tokens[0] if tokens else ""


def get_func_param_strs(cmd: str, param_count: int):
    if param_count <= 0:
        return None
    cmd = cmd.strip()
    if cmd == "":
        return []
    if param_count == 1:
        tokens = tokenize_cmd(cmd)
        if len(tokens) == 1:
            return tokens
        return [cmd]
    return tokenize_cmd(cmd)


def split_cmd(cmd: str):
    stripped = cmd.lstrip()
    if stripped == "":
        return "", "", []
    tokens = tokenize_cmd(stripped)
    if not tokens:
        return "", "", []
    token = tokens[0]
    if stripped.startswith(token):
        remainder = stripped[len(token):].lstrip()
    else:
        remainder = " ".join(tokens[1:])
    return token, remainder, tokens
