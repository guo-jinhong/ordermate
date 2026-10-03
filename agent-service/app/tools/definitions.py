TOOLS = [
    {
        "type": "function",
        "name": "update_cart_items",
        "description": "Set the quantity of all selected shopping-cart items. Read get_cart first for current cart IDs. Requires login; execute directly and verify. Does not change inventory.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "properties": {
                        "cart_id": {"type": "integer", "minimum": 1},
                        "quantity": {"type": "integer", "minimum": 1}
                    }, "required": ["cart_id", "quantity"], "additionalProperties": False
                }},
                "quantity": {"type": "integer", "minimum": 1}
            },
            "required": ["items", "quantity"], "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "search_knowledge_base",
        "description": (
            "Search knowledge bases. Two isolated stores exist: 'rule' for after-sales "
            "policy, refund/shipping/warranty rules and platform FAQ; 'product' for "
            "product attribute snippets (brand, model, specs, selling points). Choose the "
            "store matching the user's intent — the server also routes by intent and may "
            "override this parameter. Do not use this tool for real-time product price, "
            "stock, cart, or order data."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Natural-language policy/manual query.",
                },
                "kb": {
                    "type": "string",
                    "enum": ["rule", "product"],
                    "description": (
                        "Knowledge store to search: 'rule' for after-sales/policy/FAQ, "
                        "'product' for product attribute snippets. Defaults to 'rule'."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_products",
        "description": (
            "Search live products through the Java backend. Mandatory for any user request "
            "about product recommendation, product list, product price, price range, stock, "
            "availability, budget, or whether an item is sold. Extract numeric filters into "
            "min_price/max_price/in_stock instead of putting them in keyword. Use created_after "
            "for release-date or listed-after questions."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": (
                        "Product keyword/category only, preferably the user's original term, "
                        "for example 手机, 耳机, 充电宝, 笔记本, 电脑, 水杯, 运动鞋. "
                        "Use an empty string for generic product recommendations."
                    ),
                },
                "min_price": {
                    "type": "number",
                    "description": (
                        "Minimum price in CNY. Use for phrases like 4000以上, 高于4000, "
                        "at least 4000."
                    ),
                },
                "max_price": {
                    "type": "number",
                    "description": (
                        "Maximum price in CNY. Use for phrases like 4000以内, 不超过4000, "
                        "预算4000, under 4000."
                    ),
                },
                "in_stock": {
                    "type": "boolean",
                    "description": (
                        "true means only products with stock > 0. Use when the user asks "
                        "whether an item is in stock or only wants available products."
                    ),
                },
                "created_after": {
                    "type": "string",
                    "description": (
                        "ISO date or datetime lower bound for product created/listed time, "
                        "for example 2026-07-01 or 2026-07-01T00:00:00. Use when the user "
                        "asks for products released, listed, or added after a date/month."
                    ),
                },
            },
            "required": ["keyword"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_product_detail",
        "description": "Get live details for one product by product ID.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Product ID.",
                }
            },
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_cart",
        "description": "Get the current logged-in user's shopping cart. Requires login.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "add_to_cart",
        "description": "Add a product to the current logged-in user's shopping cart. Requires login.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Product ID.",
                },
                "quantity": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Quantity. The service enforces the maximum quantity.",
                },
            },
            "required": ["product_id", "quantity"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "update_cart",
        "description": (
            "Change the quantity of one item in the current logged-in user's cart. Execute directly and verify the result."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "cart_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Shopping-cart item ID.",
                },
                "quantity": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "New quantity.",
                },
            },
            "required": ["cart_id", "quantity"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "remove_from_cart",
        "description": (
            "Remove one item from the current logged-in user's cart. Execute directly and verify the result."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "cart_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Shopping-cart item ID.",
                }
            },
            "required": ["cart_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "clear_cart",
        "description": (
            "Prepare clearing the current logged-in user's shopping cart. Requires login "
            "and explicit user confirmation before execution."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_my_orders",
        "description": "List the current logged-in user's orders. Requires login.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_order_detail",
        "description": "Get one order's live details for the current logged-in user. Requires login.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Order ID.",
                }
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "cancel_order",
        "description": (
            "Prepare cancelling the current logged-in user's pending order. Requires login "
            "and explicit user confirmation before execution."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Order ID.",
                }
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "create_order",
        "description": (
            "Prepare creating an order with the current user's default shipping address "
            "(or first saved address if no default exists) and DEMO payment method. "
            "Requires login and explicit user confirmation before execution."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Product ID.",
                },
                "quantity": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Quantity.",
                },
            },
            "required": ["product_id", "quantity"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "pay_order",
        "description": (
            "Prepare confirming payment for the current logged-in user's order. Requires "
            "login and explicit user confirmation before execution."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Order ID.",
                }
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
]
