import screen_converter
import yaml
from pathlib import Path


class Converter:
    def __init__(self, config_file, test):
        self.test = test
        self.screen_path_mapping: list[tuple] = []
        self.get_config(config_file)

    def get_config(self, config_file):
        # get useful data out of json
        with open(config_file, "r") as file:
            data = yaml.safe_load(file)
            domain = data["meta_data"][0]["domain"]
            print(f"Getting config data for domain: {domain}")
            file_data = data["files"]
            for path_data in file_data:
                src_path = Path(path_data["src"])
                dst_path = Path(path_data["dst"])
                if src_path.is_dir():
                    src_files = src_path.iterdir()
                else:
                    src_files = [src_path]

                if self.test:
                    # If in testing mode, output files to current directory/output
                    dst_path = Path.cwd() / "output"
                    dst_path.mkdir(exist_ok=True)
                    
                for src_file in src_files:
                    if src_file.suffix == ".opi":
                        self.screen_path_mapping.append((src_file, dst_path))

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
            screen_converter.main(screen_src, screen_dst)
            # # Update filepaths
            # self.update_filepaths()
            # # Update macros
            # self.update_macros()
            # # Convert to techui-builder?
            # self.convert_to_techui_builder()


def main(
    config_file=Path.cwd() / "config" / "front-ends.yaml",
    test=True,
):
    converter = Converter(config_file, test)
    converter.convert()


if __name__ == "__main__":
    main()
