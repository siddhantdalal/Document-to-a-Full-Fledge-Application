from packages.generator.naming import pascal, plural, snake


def test_snake_handles_pascal():
    assert snake("UserAccount") == "user_account"
    assert snake("APIKey") == "api_key"
    assert snake("HTTPServer") == "http_server"


def test_snake_handles_kebab_and_spaces():
    assert snake("user-account") == "user_account"
    assert snake("user account") == "user_account"


def test_snake_strips_punctuation():
    assert snake("Todo!") == "todo"
    assert snake("My Todo App") == "my_todo_app"


def test_pascal_from_snake():
    assert pascal("user_account") == "UserAccount"


def test_pascal_from_kebab():
    assert pascal("user-account") == "UserAccount"


def test_plural_basic():
    assert plural("todo") == "todos"
    assert plural("user") == "users"


def test_plural_y_ending_after_consonant():
    assert plural("category") == "categories"
    assert plural("entity") == "entities"


def test_plural_y_ending_after_vowel():
    assert plural("toy") == "toys"


def test_plural_sibilant_endings():
    assert plural("class") == "classes"
    assert plural("box") == "boxes"
    assert plural("dish") == "dishes"
