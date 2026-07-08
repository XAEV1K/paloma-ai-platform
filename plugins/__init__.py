"""Plugin SDK surface.

Third-party capabilities live here. The contract is three imports and a
decorator — the platform does the rest (discovery, dependency injection,
instrumentation, capability mapping)::

    from pydantic import BaseModel, Field
    from tools.base import InstrumentedTool, register_tool

    class MyInput(BaseModel):
        restaurant_id: str = Field(description="...")

    @register_tool
    class MyTool(InstrumentedTool):
        name: str = "my_tool"
        description: str = "What the model reads to decide when to call it."
        args_schema: type[BaseModel] = MyInput
        # declare dependencies as fields; the composition root injects them
        restaurant_service: "RestaurantService"

        def _execute(self, restaurant_id: str) -> str:
            ...

See ``loyalty_insights.py`` for a complete working example.
"""
