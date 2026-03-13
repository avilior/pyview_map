from .models.dlist_item import DListItem

__all__ = ["DListItem"]


def __getattr__(name):
    if name == "DynamicListComponent":
        from .dynamic_list import DynamicListComponent
        return DynamicListComponent
    if name == "DynamicListLiveView":
        from .dynamic_list import DynamicListLiveView
        return DynamicListLiveView
    if name == "ListDriver":
        from .list_driver import ListDriver
        return ListDriver
    if name in ("ItemRenderer", "default_item_renderer"):
        from .dynamic_list import ItemRenderer, default_item_renderer
        return ItemRenderer if name == "ItemRenderer" else default_item_renderer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
