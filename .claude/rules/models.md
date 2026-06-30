---
paths:
  - "app/models/**/*.py"
---

# Pydantic Schema Rules

- Always use Pydantic v2 syntax: `model_config = ConfigDict(from_attributes=True)` for ORM schemas
- Response schemas must always include `id: int` and inherit from the base schema
- Update schemas (PATCH) must mark all fields as `Optional` with `default=None`
- Field validation constraints: name 1-100 chars, description 1-500 chars, price > 0, quantity >= 0
- Never use `float` for monetary fields — use `Decimal` with `condecimal(max_digits=10, decimal_places=2)`
- Separate Create / Update / Response schemas — never reuse the same schema for input and output
