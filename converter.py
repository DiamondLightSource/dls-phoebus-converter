import screen_converter


class Converter:
    def __init__(self):
        self.screen_path_mapping: list[tuple]
        self.get_config()

    def get_config(self, config_file) -> list[tuple]:
        #get useful data out of json
        self.screen_path_mapping = [("src/path", "dst/path")]
        pass

    def update_filepaths(self):
        # for line in xml file
        #   if <file> or <image-file> in line:
        #       Update path to new path somehow
        pass

    def update_macros(self):
        # If synoptic screen
        #   if macro in line:
        #       if macro is in our config data
        #           macro = macro_value
        #       else:
        #           raise error
        pass

    def convert_to_techui_builder(self):
        pass

    def convert(self):
        for screen_src, screen_dst in self.screen_path_mapping:
            # Convert .boy to .bob
            screen_converter.main()
            # Update filepaths
            self.update_filepaths()
            # Update macros
            self.update_macros()
            # Convert to techui-builder?
            self.convert_to_techui_builder()


def main(config_file):
    converter = Converter(config_file)
    converter.convert()
