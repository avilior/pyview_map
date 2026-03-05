from .dlist_item import DListItem

__all__ = ["DListItem"]


def __getattr__(name):
    if name == "DynamicListComponent":
        from .dynamic_list import DynamicListComponent
        return DynamicListComponent
    if name == "DynamicListLiveView":
        from .dynamic_list import DynamicListLiveView
        return DynamicListLiveView
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
