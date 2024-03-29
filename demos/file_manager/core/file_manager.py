import math
import os
import platform
import psutil

from demos.file_manager.utils.table import Table


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_names = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s}{size_names[i]}"


class OS:
    def __init__(self):
        # 获取操作系统的友好名称
        self.os_name = platform.system()
        # 获取操作系统的详细版本信息
        self.os_version = platform.version()
        # 获取操作系统的发行版
        self.os_release = platform.release()
        # 获取操作系统的网络名称
        self.node_name = platform.node()
        # 获取操作系统的硬件架构
        self.architecture = platform.architecture()
        # 获取完整的操作系统信息
        self.full_os_info = platform.uname()


class Manager:
    def __init__(self):
        self.os = OS()
        self.workspace = os.path.dirname(os.path.abspath(__file__))
        self._local_env()
        self.disk_list = []

    @property
    def env_keys(self):
        return ["disk", "os", "network"]

    def _local_env(self):
        self.disk_partitions = psutil.disk_partitions(all=True)
        self.net_addrs = psutil.net_if_addrs()

    def display_os(self):
        title = "OS Information"
        header = ["Env Info", "Value", "Description"]
        data = [
            ["OS Name", self.os.os_name, "操作系统的友好名称"],
            ["OS Version", self.os.os_version, "操作系统的详细版本信息"],
            ["OS Release", self.os.os_release, "操作系统的发行版"],
            ["OS Node Name", self.os.node_name, "操作系统的网络名称"],
            ["OS Architecture", self.os.architecture, "操作系统的硬件架构"],
            ["OS Full Info", self.os.full_os_info, "完整的操作系统信息"]
        ]
        return Table(header, data, title)

    def display_disks(self):
        title = "Disks Information"
        header = ["Device", "Mount Point", "File System Type", "Total", "Used", "Free", "Percent"]
        data = []
        for partition in self.disk_partitions:
            device = partition.device
            mount_point = partition.mountpoint
            fs_type = partition.fstype
            if fs_type is None:
                fs_type = "None"
            try:
                usage = psutil.disk_usage(mount_point)
                total = convert_size(usage.total)
                used = convert_size(usage.used)
                free = convert_size(usage.free)
                percent = str(usage.percent) + "%"
                data.append([device, mount_point, fs_type, total, used, free, percent])
            except PermissionError:
                data.append([device, mount_point, fs_type, "Access denied", "Access denied", "Access denied", "Access denied"])
        return Table(header, data, title)

    def display_network(self):
        title = "Network Interface Information"
        header = ["Interface Name", "Address", "Netmask", "Broadcast"]
        data = []
        for if_name in self.net_addrs:
            data.append([if_name, "", "", ""])
            for snic in self.net_addrs[if_name]:
                data.append(["", snic.address, snic.netmask, snic.broadcast])
        return Table(header, data, title)
