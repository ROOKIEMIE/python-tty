cmd_split_type = " "


def get_command_token(cmd: str):
    if cmd_split_type not in cmd:
        return cmd
    index = cmd.find(cmd_split_type)
    return cmd[:index] if index != -1 else cmd


def get_func_param_strs(cmd: str, param_count: int):
    if param_count <= 0:
        return None
    split_count = cmd.count(cmd_split_type) + 1
    if split_count > 0 and param_count == 1:
        return [cmd]
    return cmd.split(cmd_split_type)

