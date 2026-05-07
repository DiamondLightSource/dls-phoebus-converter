"""Helper functions for non specific conversion use"""


def search_widget_filepaths_recursive(
    widget, func: typing.Callable, widget_file_paths=None, macros=None
):
    """This generic, recursive function takes a widget and searches for any
    references to filepaths these can be in multiple different widget fields and
    also in widgets within the widget etc. When a filepath is found, it is passed
    into the passed func callable."""

    args = [arg for arg in [widget_file_paths, macros] if arg is not None]

    if not isinstance(widget, dict):
        return
    if "widget" in widget:
        for child in widget["widget"]:
            search_widget_filepaths_recursive(child, func, widget_file_paths, macros)
    if "tabs" in widget:
        for tab in widget["tabs"]["tab"]:
            # widget["tabs"]["tab"] can either be a single tab or a list of tabs, so
            # we have to handle this by checking the type of tab
            if type(tab) is str:
                for child_widget in widget["tabs"]["tab"]["children"]["widget"]:
                    if type(child_widget) is str:
                        search_widget_filepaths_recursive(
                            widget["tabs"]["tab"]["children"]["widget"],
                            func,
                            widget_file_paths,
                            macros,
                        )
                        break
                    search_widget_filepaths_recursive(
                        child_widget, func, widget_file_paths, macros
                    )
                break
            if "children" in tab and tab["children"] is not None:
                for child_widget in tab["children"]["widget"]:
                    if type(child_widget) is str:
                        search_widget_filepaths_recursive(
                            tab["children"]["widget"],
                            func,
                            widget_file_paths,
                            macros,
                        )
                        break
                    search_widget_filepaths_recursive(
                        child_widget, func, widget_file_paths, macros
                    )

    if "symbols" in widget:
        for symbol_widget_name in widget["symbols"]:
            symbol_widget = widget["symbols"][symbol_widget_name]
            if symbol_widget != [None, None]:
                if isinstance(symbol_widget, list):
                    for i, symbol_path in enumerate(symbol_widget):
                        if func(Path(symbol_path), *args, symbol=True):
                            symbol_widget[i] = func(
                                Path(symbol_path), *args, symbol=True
                            )
                else:
                    # We only log when we find an edm widget not when we later
                    # switch it
                    if func.__name__ == "append_new_filepath":
                        logger.warning(
                            "Warning, edm style symbol widget detected: "
                            f"{widget['name']}"
                        )
                    if func(Path(symbol_widget), *args, symbol=True):
                        widget["symbols"]["symbol"] = func(
                            Path(symbol_widget), *args, symbol=True
                        )
    if "file" in widget and widget["file"] is not None:
        if func(Path(widget["file"]), *args):
            widget["file"] = func(Path(widget["file"]), *args)
    if "opi_file" in widget and widget["opi_file"] is not None:
        if func(Path(widget["opi_file"]), *args):
            widget["opi_file"] = func(Path(widget["opi_file"]), *args)
    if "actions" in widget and widget["actions"] is not None:
        for action in widget["actions"]:
            if (
                "path" in widget["actions"][action]
                and widget["actions"][action]["path"] is not None
            ):
                if func(Path(widget["actions"][action]["path"]), *args):
                    widget["actions"][action]["path"] = func(
                        Path(widget["actions"][action]["path"]), *args
                    )
            elif (
                "file" in widget["actions"][action]
                and widget["actions"][action]["file"] is not None
            ):
                if func(Path(widget["actions"][action]["file"]), *args):
                    widget["actions"][action]["file"] = func(
                        Path(widget["actions"][action]["file"]), *args
                    )
    return widget_file_paths
