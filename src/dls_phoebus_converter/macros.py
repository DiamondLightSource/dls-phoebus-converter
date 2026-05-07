"""Manages the conversion of existing macros and addition of new macros"""

MACRO_EXCEPTION_LIST = ["pv_name", "pv_value", "name", "actions"]


def fill_in_file_path_macros(self, string: str, macros) -> str:
    def replace(match):
        key = match.group(1)  # the ‘x’ inside ${x}
        return macros.get(key, match.group(0))  # default: leave unchanged

    resolved_path = re.sub(r"\$[\{\(]([^\}\)\s]+)[\}\)]", replace, str(string))
    return resolved_path


def add_new_macros(
    self,
    conversion: ConversionConfig,
    macro_names: list[str],
    macro_values: list[str],
) -> None:
    """Add a list of macro name/values to the top level of the bob file."""

    if "macros" not in conversion.all_phoebus_data["display"]:
        conversion.all_phoebus_data["display"]["macros"] = {}

    macro_data = conversion.all_phoebus_data["display"]["macros"]

    for new_macro_name, new_macro_value in zip(macro_names, macro_values, strict=True):
        for existing_macro_name, existing_macro_value in macro_data.items():
            if existing_macro_name == new_macro_name:
                logging.warning(
                    f"An existing file macro is being overwritten: "
                    f"{existing_macro_name}:{existing_macro_value} -> "
                    f"{new_macro_name}:{new_macro_value}"
                )
        macro_data[new_macro_name] = new_macro_value

    conversion.widget_data = conversion.all_phoebus_data["display"]["widget"]


def handle_macros(self, file_path: Path, conversion: ConversionConfig) -> None:
    """Look for unique instances of a macro eg ${string} in the bob file. We ignore
    a small number of macros which are defined from other widget fields
    (MACRO_EXCEPTION_LIST). If a macro is found in a file but has not been defined
    in the ConversionConfig, then we log a warning."""

    new_macro_names = []
    new_macro_values = []

    with file_path.open("r", encoding="utf-8") as fh:
        content = fh.read()

    identified_macros = re.findall(r"\$[\{\(]([^\}\)\s]+)[\}\)]", content)

    unique_identified_macros = list(dict.fromkeys(identified_macros))
    logger.info(f"Found macros in file: {unique_identified_macros}")

    for macro in unique_identified_macros:
        # Some macros refer to internal Phoebus objects, so we dont resolve these
        if macro not in MACRO_EXCEPTION_LIST:
            if macro in conversion.macros.keys():
                new_macro_names.append(macro)
                new_macro_values.append(conversion.macros[macro])
            else:
                # This macro has not been defined!
                logger.warning(
                    f"Could not find definition for macro: '{macro}'. "
                    "Should this have been defined in your yaml config?"
                )

    # Add macros defined in config even if they are not used in the parent display
    for m_name, m_key in conversion.macros.items():
        if m_name not in new_macro_names:
            new_macro_names.append(m_name)
            new_macro_values.append(m_key)

    self.add_new_macros(conversion, new_macro_names, new_macro_values)
