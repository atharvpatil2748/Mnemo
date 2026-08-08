import docx


def test_images():
    doc = docx.Document()
    doc.add_picture(
        "C:/Users/athar/Desktop/Mnemo/mnemo-core/tests/fixtures/sample.pdf"
    )  # wait, add a dummy picture or just iterate parts

    print("Parts:", [p for p in doc.part.related_parts.values()])


if __name__ == "__main__":
    test_images()
