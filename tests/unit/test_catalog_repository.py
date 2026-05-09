from app.repositories.catalog import InMemoryCatalogRepository


def test_catalog_repository_lists_tables() -> None:
    repository = InMemoryCatalogRepository.with_demo_data()

    database = repository.get_database("demo")
    spaces = repository.list_spaces("demo")
    tables = repository.list_tables("demo", "sales")

    assert database.id == "demo"
    assert spaces[0].id == "sales"
    assert tables[0].name == "sales_orders"
