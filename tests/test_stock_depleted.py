import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.auth import identidade
from app.repository.pgsql.stock import StockRepository
from app.tools import pg_tools, recipe_tools


class _Rows:
    def all(self):
        return []


class _QueryCapture:
    def __init__(self):
        self.statements = []

    def scalars(self, statement):
        self.statements.append(statement)
        return _Rows()

    def execute(self, statement):
        self.statements.append(statement)
        return _Rows()


class DepletedPantryTest(unittest.TestCase):
    def test_reads_that_claim_available_stock_ignore_zero_or_negative_rows(self):
        session = _QueryCapture()
        repository = StockRepository(session)

        repository.get_stock(124)
        repository.get_expired_products(124)
        repository.get_missing_products(124)
        repository.get_category_info(124)
        repository.get_brand_info(124)

        self.assertEqual(len(session.statements), 5)
        sql_statements = [
            str(statement.compile(compile_kwargs={"literal_binds": True})).lower()
            for statement in session.statements
        ]
        # Zero rows are not available stock or expirables, but must remain in
        # the low-stock calculation so a configured minimum reports them.
        for sql in (*sql_statements[:2], *sql_statements[3:]):
            self.assertIn("pantry_item.quantity > 0", sql)
        self.assertNotIn("pantry_item.quantity > 0", sql_statements[2])
        self.assertIn("coalesce(sum(pantry_item.quantity), 0) <", sql_statements[2])
        self.assertIn("left outer join pantry_item", sql_statements[2])
        self.assertIn("coalesce(sum(pantry_item.quantity), 0)", sql_statements[2])

    def test_zero_quantity_row_is_a_confirmed_shortage_for_recipe_calculation(self):
        result = recipe_tools.calculate_missing(
            [{"name": "Leite", "quantity": "200 ml"}],
            [{"food_name": "Leite", "quantity": 0, "unit_of_measure": "l",
              "package_quantity": 1, "expiry_date": None}],
            date(2026, 11, 2),
        )

        self.assertTrue(result["conferencia"][0]["comparacao_confirmada"])
        self.assertFalse(result["conferencia"][0]["tem_suficiente"])
        self.assertEqual(result["itens_para_comprar"], [
            {"name": "Leite", "quantity": 200.0, "unitOfMeasure": "ml", "checked": False},
        ])

    def test_remove_product_physically_deletes_even_a_zero_balance_pantry_row(self):
        item = SimpleNamespace(profile_id=124, quantity=0)
        removed = []

        class Repository:
            def __init__(self, _session):
                pass

            def find_by_id(self, _item_id):
                return item

            def remove_product(self, pantry_item):
                removed.append(pantry_item)
                return True

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with patch.object(pg_tools, "StockRepository", Repository), \
                patch.object(pg_tools, "SessionLocal", Session), \
                identidade.da_requisicao(124, 124):
            result = pg_tools.remove_product.invoke({"pantry_item_id": 23})

        self.assertIs(result, True)
        self.assertEqual(removed, [item])

    def test_repository_commits_physical_delete_for_zero_balance_item(self):
        item = SimpleNamespace(quantity=0)

        class Session:
            deleted = None
            committed = False

            def delete(self, value):
                self.deleted = value

            def commit(self):
                self.committed = True

        session = Session()
        result = StockRepository(session).remove_product(item)

        self.assertTrue(result)
        self.assertIs(session.deleted, item)
        self.assertTrue(session.committed)

    def test_missing_stock_report_never_returns_negative_available_quantity(self):
        class Repository:
            def __init__(self, _session):
                pass

            def get_missing_products(self, _profile_id):
                return [SimpleNamespace(food_id=5, quantity=-2, minimum_quantity=3)]

        class FoodRepository:
            def __init__(self, _session):
                pass

            def get_foods(self):
                return [SimpleNamespace(id=5, name="Leite")]

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with patch.object(pg_tools, "StockRepository", Repository), \
                patch.object(pg_tools, "FoodRepository", FoodRepository), \
                patch.object(pg_tools, "SessionLocal", Session), \
                identidade.da_requisicao(124, 124):
            result = json.loads(pg_tools.get_missing_products.invoke({}))

        self.assertEqual(result[0]["quantity"], 0)
