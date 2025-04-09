import re
from docstr_coverage import get_docstring_coverage
from functions import find_between


def main():
    try:
        readmePath = "readme.md"

        my_coverage = get_docstring_coverage(["app.py"])

        with open("doc_output.txt", "w") as out:
            score = int(str(my_coverage[0]["app.py"]["coverage"]).split(".")[0])

            # if score is less than 50 - color is red
            if score < 50:
                color = "red"
            # if score is less than 70 - color is orange
            elif score < 70:
                color = "orange"
            # if score is less than 90 - color is yellow
            elif score < 90:
                color = "yellow"
            # if score is greater than 90 - color is green\
            else:
                color = "green"

            output_url = f"https://img.shields.io/badge/docstr_coverage-{score}-{color}"
            print(output_url)

        # Read the readme file
        with open(readmePath, "r") as f:
            text = f.read()
        old_version_badge = find_between(
            str(text),
            "<!-- Start Docstring Coverage Badges -->",
            "<!-- End Docstring Coverage Badges -->",
        )

        new_badge = f"\n<img loading='lazy' src='{output_url}' class='img_ev3q'>\n"

        updated_readme_str = str(text).replace(old_version_badge, new_badge)

        # Writing the updated readme file
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
