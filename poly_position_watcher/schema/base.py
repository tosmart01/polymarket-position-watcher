# -*- coding = utf-8 -*-
# @Time: 2025-12-06 19:09:43
# @Author: Donvink wuwukai
# @Site:
# @File: base.py
# @Software: PyCharm
from datetime import datetime

from pydantic import BaseModel, ConfigDict


def datetime_to_gmt_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class PrettyPrintBaseModel(BaseModel):
    def __str__(self):
        # 将每个字段和值分行显示
        lines = [f"{name}: {value!r}" for name, value in self.__dict__.items()]
        return f"{self.__class__.__name__}(\n  " + ",\n  ".join(lines) + "\n)"

    # 可选：让 repr() 打印同样效果
    __repr__ = __str__
    model_config = ConfigDict(
        json_encoders={datetime: datetime_to_gmt_str},
        populate_by_name=True,
    )
