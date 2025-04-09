import os
import json
import re
from functions import find_between


def main():
    try:
        # local testing paths
        coveragePath = "coverage.json"
        readmePath = "readme.md"

        # Reading the JSON file
        with open(coveragePath, "r") as f:
            data = json.load(f)

        # Get the coverage value and create badge with value
        coverage = data["totals"]["percent_covered_display"]
        output_url = f"https://img.shields.io/badge/coverage-{coverage}-green"

        # Read the readme file
        with open(readmePath, "r") as f:
            text = f.read()
        old_version_badge = find_between(
            str(text),
            "<!-- Start Code Coverage Badges -->",
            "<!-- End Code Coverage Badges -->",
        )

        new_badge = f"\n<img loading='lazy' src='{output_url}' class='img_ev3q'>\n"

        updated_readme_str = str(text).replace(old_version_badge, new_badge)

        # Writing Readme
        with open(readmePath, "w") as f:
            f.write(updated_readme_str)
            print("READme successfully edited")
        return True

    except Exception as e:
        print(e)
        print("Something went wrong editing the READme version")
        return False


if __name__ == "__main__":
    main()
