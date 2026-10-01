#!/usr/bin/env python3
"""
caloriebase - static site generator
Parses USDA SR Legacy ASCII files and emits a fully static, SEO-ready site.

Data source: USDA National Nutrient Database for Standard Reference, Legacy
Release (public domain, CC0). Files parsed here:

    FOOD_DES.txt   food records (NDB_No, FdGrp_Cd, Long_Desc, ...)
    FD_GROUP.txt   food group code -> name
    NUT_DATA.txt   nutrient values per food (nutrient number, value)
    NUTR_DEF.txt   nutrient number -> name/unit
    WEIGHT.txt     common serving measures (g weight per measure)

Usage:
    python src/generate.py [--top N] [--out DIR]
"""

import argparse
import json
import os
import re
import shutil
import sys
from html import escape

BASE_URL = "https://caloriebase.austinnu22.workers.dev"
SITE_NAME = "CalorieBase"
SITE_TAGLINE = "Calorie & nutrition database for thousands of foods"

# Nutrient numbers used from NUTR_DEF.txt
NUTRIENTS = {
    "208": ("Energy", "kcal"),       # kcal per 100 g
    "203": ("Protein", "g"),
    "204": ("Total lipid (fat)", "g"),
    "205": ("Carbohydrate, by difference", "g"),
    "291": ("Fiber, total dietary", "g"),
    "269": ("Sugars, total", "g"),
    "307": ("Sodium, Na", "mg"),
    "306": ("Potassium, K", "mg"),
    "301": ("Calcium, Ca", "mg"),
    "303": ("Iron, Fe", "mg"),
}

# Common foods likely to have real search demand (match against food name).
# The generator includes foods matching these terms in the starter build.
POPULAR_TERMS = [
    "apple", "banana", "orange", "grape", "strawberr", "blueberr", "raspberr",
    "cherries", "peach", "pear", "plum", "watermelon", "pineapple", "mango",
    "avocado", "lemon", "lime", "coconut", "kiwi", "melon",
    "carrot", "broccoli", "spinach", "kale", "lettuce", "cabbage", "cauliflower",
    "potato", "sweet potato", "tomato", "onion", "garlic", "pepper", "cucumber",
    "corn", "peas", "green beans", "celery", "mushroom", "squash", "zucchini",
    "eggplant", "beet", "radish", "asparagus", "brussels sprout", "artichoke",
    "chicken", "beef", "pork", "lamb", "turkey", "bacon", "ham", "sausage",
    "steak", "ground beef", "chicken breast", "chicken thigh", "chicken wing",
    "salmon", "tuna", "cod", "tilapia", "shrimp", "crab", "lobster", "scallop",
    "trout", "sardine", "mackerel", "halibut", "flounder", "catfish", "clam",
    "egg", "milk", "cheese", "cheddar", "mozzarella", "parmesan", "swiss cheese",
    "american cheese", "yogurt", "butter", "cream", "sour cream", "cottage cheese",
    "whipping cream", "ice cream", "frozen yogurt",
    "bread", "white bread", "whole wheat bread", "bagel", "muffin", "croissant",
    "tortilla", "pita", "roll", "bun", "cracker", "pretzel", "pancake",
    "waffle", "pizza", "pasta", "spaghetti", "macaroni", "lasagna", "noodles",
    "rice", "brown rice", "white rice", "quinoa", "oats", "oatmeal", "barley",
    "cereal", "cornflakes", "granola", "couscous", "lentil", "bean", "chickpea",
    "kidney bean", "black bean", "pinto bean", "tofu", "tempeh", "hummus",
    "nuts", "almond", "walnut", "peanut", "cashew", "pecan", "pistachio",
    "hazelnut", "macadamia", "peanut butter", "almond butter", "sunflower seed",
    "pumpkin seed", "chia seed", "flaxseed", "sesame seed",
    "honey", "sugar", "brown sugar", "molasses", "maple syrup", "jam", "jelly",
    "chocolate", "cocoa", "dark chocolate", "milk chocolate", "cookie",
    "brownie", "cake", "cheesecake", "donut", "pie", "candy", "gummi",
    "popcorn", "chips", "potato chips", "tortilla chips", "french fries",
    "fries", "onion rings", "burger", "sandwich", "hot dog", "taco", "burrito",
    "soup", "broth", "chili", "stew", "curry", "fried rice", "dumpling",
    "mayonnaise", "ketchup", "mustard", "salsa", "guacamole", "ranch",
    "olive oil", "vegetable oil", "coconut oil", "canola oil", "sunflower oil",
    "peanut oil", "sesame oil", "butter", "margarine",
    "coffee", "tea", "espresso", "cappuccino", "latte", "hot chocolate",
    "cola", "soda", "coke", "sprite", "lemonade", "orange juice", "apple juice",
    "grape juice", "cranberry juice", "tomato juice", "milk shake", "smoothie",
    "beer", "wine", "red wine", "white wine", "vodka", "whiskey", "rum", "gin",
    "beer", "champagne", "hard cider",
    "steak", "ribs", "brisket", "chuck", "sirloin", "tenderloin", "top round",
    "ham", "prosciutto", "salami", "pepperoni", "hot sauce", "barbecue sauce",
    "soy sauce", "vinegar", "olive", "pickle", "dill pickle", "sauerkraut",
    "tomato sauce", "marinara", "spaghetti sauce", "cream cheese", "ricotta",
    "feta", "brie", "gouda", "provolone", "blue cheese", "goat cheese",
    "egg white", "egg yolk", "omelet", "scrambled egg", "poached egg",
    "oat milk", "almond milk", "soy milk", "rice milk", "coconut milk",
    "sweetened condensed milk", "evaporated milk", "half and half", "kefir",
    "avocado toast", "breakfast cereal", "instant oatmeal", "grits", "polenta",
    "ramen", "udon", "soba", "sushi", "sashimi", "edamame", "wasabi", "ginger",
    "garlic bread", "sourdough", "rye bread", "multigrain", "cornbread", "biscuit",
    "english muffin", "toast", "cinnamon roll", "pop tart", "granola bar",
    "protein bar", "energy bar", "fruit snack", "dried apple", "raisin",
    "prune", "date", "fig", "apricot", "cranberries", "sweetened cranberries",
    "dark cherries", "pomegranate", "grapefruit", "tangerine", "mandarin",
    "plantain", "yucca", "turnip", "rutabaga", "parsnip", "jicama",
]

STOPWORDS = {"with", "and", "for", "without", "added", "raw", "cooked", "from",
             "the", "prepared", "as", "to", "not", "nfs", "usda", "generic",
             "includes", "foods", "food", "distribution", "program",
             "commercially", "regular", "all", "varieties", "unspecified"}

# Curated base names for the launch set (highest real-world search demand).
# Each entry matches the first segment of USDA food names (case-insensitive).
CURATED_BASES = [
    "apples", "bananas", "oranges", "strawberries", "grapes", "watermelon",
    "pineapple", "mango", "peaches", "plums", "cherries", "pears", "kiwi fruit",
    "avocados", "lemons", "limes", "cantaloupe", "honeydew melon", "cranberries",
    "blueberries", "raspberries", "blackberries", "papayas", "figs", "dates",
    "prunes", "raisins", "coconuts", "grapefruit", "tangerines", "canned fruit cocktail",
    "carrots", "broccoli", "cauliflower", "spinach", "kale", "lettuce", "cabbage",
    "tomatoes", "potatoes", "sweet potato", "onions", "garlic", "bell peppers",
    "cucumbers", "corn", "peas", "green beans", "celery", "mushrooms", "zucchini",
    "summer squash", "winter squash", "eggplant", "beets", "radishes", "asparagus",
    "brussels sprouts", "artichokes", "okra", "turnips", "parsnips", "rutabagas",
    "pumpkin", "sweet peppers", "chili peppers", "jalapeno peppers",
    "chicken", "chicken breast", "chicken thigh", "chicken wing", "chicken leg",
    "chicken drumstick", "turkey", "turkey breast", "turkey bacon", "turkey sausage",
    "beef", "ground beef", "beef steak", "beef rib", "beef tenderloin", "beef top sirloin",
    "beef chuck", "beef brisket", "beef flank", "beef round", "corned beef", "beef liver",
    "pork", "pork chop", "pork loin", "pork shoulder", "pork belly", "bacon",
    "ham", "sausage", "italian sausage", "bratwurst", "chorizo", "hot dog", "salami",
    "pepperoni", "prosciutto", "lamb", "lamb chop", "veal", "bison", "venison",
    "salmon", "tuna", "cod", "tilapia", "shrimp", "crab", "lobster", "scallops",
    "trout", "sardines", "mackerel", "halibut", "flounder", "catfish", "clams",
    "oysters", "mussels", "anchovies", "crayfish", "lobster",
    "egg", "egg white", "egg yolk", "milk", "buttermilk", "whole milk", "skim milk",
    "lowfat milk", "2% milk", "1% milk", "goat milk", "coconut milk",
    "cheese", "cheddar cheese", "mozzarella", "parmesan", "swiss cheese",
    "american cheese", "provolone", "feta cheese", "blue cheese", "brie cheese",
    "ricotta", "cottage cheese", "cream cheese", "monterey cheese", "gouda",
    "yogurt", "greek yogurt", "butter", "margarine", "whipped cream", "cream",
    "sour cream", "half and half", "ice cream", "frozen yogurt", "pudding",
    "bread", "white bread", "whole wheat bread", "rye bread", "pumpernickel",
    "sourdough", "bagel", "english muffin", "croissant", "muffin", "biscuit",
    "cornbread", "roll", "dinner roll", "hot dog bun", "hamburger bun", "tortilla",
    "pita bread", "naan", "flatbread", "cracker", "saltine crackers", "pretzels",
    "rice", "white rice", "brown rice", "wild rice", "jasmine rice", "basmati rice",
    "fried rice", "risotto", "pasta", "spaghetti", "macaroni", "lasagna", "penne",
    "fettuccine", "linguine", "rigatoni", "noodles", "ramen", "udon", "soba",
    "macaroni and cheese", "spaghetti with meat sauce", "oats", "oatmeal", "granola",
    "cereal", "corn flakes", "wheat cereal", "oat bran", "wheat bran", "grits",
    "quinoa", "couscous", "barley", "bulgur", "farro", "millet", "amaranth",
    "lentils", "chickpeas", "kidney beans", "black beans", "pinto beans", "navy beans",
    "lima beans", "great northern beans", "black eyed peas", "split peas", "soybeans",
    "tofu", "tempeh", "hummus", "edamame", "peanut butter", "almond butter",
    "cashew butter", "almonds", "walnuts", "peanuts", "cashews", "pecans",
    "pistachios", "hazelnuts", "macadamia nuts", "brazil nuts", "pine nuts",
    "sunflower seeds", "pumpkin seeds", "chia seeds", "flaxseed", "sesame seeds",
    "honey", "sugar", "brown sugar", "powdered sugar", "molasses", "maple syrup",
    "corn syrup", "jam", "jelly", "marmalade", "peanut butter and jelly",
    "chocolate", "dark chocolate", "milk chocolate", "white chocolate", "cocoa powder",
    "chocolate chips", "candy", "gummy", "jelly beans", "caramel", "fudge",
    "marshmallows", "cookie", "chocolate chip cookie", "oatmeal cookie", "brownie",
    "cake", "cheesecake", "cupcake", "donuts", "pie", "apple pie", "pumpkin pie",
    "pecan pie", "cobbler", "crumble", "strudel", "eclair", "pudding", "gelatin dessert",
    "popcorn", "potato chips", "tortilla chips", "corn chips", "pita chips",
    "pretzels", "trail mix", "fruit snack", "granola bar", "protein bar",
    "energy bar", "candy bar", "french fries", "onion rings", "potato salad",
    "coleslaw", "macaroni salad", "pizza", "burger", "cheeseburger", "sandwich",
    "grilled cheese", "tuna sandwich", "chicken sandwich", "submarine sandwich",
    "hot dog", "taco", "burrito", "quesadilla", "enchilada", "fajita", "nacho",
    "chili con carne", "tamale", "empanada", "spring roll", "dumpling",
    "soup", "chicken soup", "tomato soup", "vegetable soup", "miso soup",
    "chicken noodle soup", "beef stew", "chili", "curry", "chow mein", "fried chicken",
    "chicken nuggets", "chicken tenders", "meatloaf", "meatball", "meat sauce",
    "mashed potatoes", "baked potato", "roasted potatoes", "hash browns",
    "sweet potato fries", "mac and cheese", "casserole",
    "mayonnaise", "ketchup", "mustard", "relish", "salsa", "guacamole", "hummus",
    "ranch dressing", "italian dressing", "ranch", "caesar dressing", "blue cheese dressing",
    "thousand island", "olive oil", "vegetable oil", "canola oil", "coconut oil",
    "sunflower oil", "sesame oil", "peanut oil", "corn oil", "safflower oil",
    "soybean oil", "grape seed oil", "avocado oil", "vinegar", "soy sauce",
    "teriyaki sauce", "hot sauce", "barbecue sauce", "steak sauce", "worcestershire sauce",
    "tomato sauce", "marinara sauce", "spaghetti sauce", "pasta sauce", "alfredo sauce",
    "pesto", "gravy", "cream of mushroom soup", "broth", "chicken broth", "beef broth",
    "vegetable broth", "stock", "bouillon", "olives", "pickles", "sauerkraut",
    "dill pickles", "sweet pickles", "salsa verde",
    "coffee", "espresso", "cappuccino", "latte", "mocha", "iced coffee",
    "tea", "green tea", "black tea", "herbal tea", "iced tea", "chai",
    "hot chocolate", "cocoa mix", "orange juice", "apple juice", "grape juice",
    "cranberry juice", "tomato juice", "pineapple juice", "grapefruit juice",
    "carrot juice", "vegetable juice", "lemonade", "punch", "cola", "soda",
    "root beer", "ginger ale", "sports drink", "energy drink", "smoothie",
    "milkshake", "coffee creamer", "coconut water", "almond milk", "soy milk",
    "oat milk", "rice milk", "milk substitute",
    "beer", "wine", "red wine", "white wine", "rosé wine", "champagne", "hard cider",
    "vodka", "whiskey", "rum", "gin", "tequila", "brandy", "liqueur",
    "olive oil", "butter", "lard", "shortening", "mayonnaise",
    "mushrooms", "truffles", "seaweed", "kelp", "soy sauce",
    "bamboo shoots", "water chestnuts", "sprouts", "bean sprouts", "alfalfa sprouts",
    "peanut sauce", "teriyaki", "wasabi", "ginger root", "turmeric", "cinnamon",
    "vanilla extract", "vanilla", "salt", "pepper", "black pepper", "garlic powder",
    "onion powder", "paprika", "chili powder", "oregano", "basil", "cilantro",
    "parsley", "dill", "mint", "rosemary", "thyme", "bay leaf", "cloves", "nutmeg",
    "ginger", "cumin", "coriander", "mustard seed", "saffron", "tarragon",
]


def base_name(name):
    """First comma-segment of a food name, cleaned (the 'apple' in 'Apples, raw')."""
    base = name.split(",")[0].strip().lower()
    return base


def primary_key(name):
    """Key used to group variants of the same food (base name)."""
    return base_name(name)


def pick_primary(variants):
    """Choose the best variant to own the short '/food/<base>/' URL.

    Prefers: fewer qualifier segments, then 'raw', then shortest name.
    """
    def score(f):
        parts = f.name.split(",")
        s = len(parts) * 100
        lower = f.name.lower()
        if "raw" in lower:
            s -= 30
        if "with skin" in lower or "whole" in lower:
            s -= 15
        if "nfs" in lower or "brand" in lower or "restaurant" in lower:
            s += 60
        s += len(f.name)
        return s
    return sorted(variants, key=score)[0]


# Words that hint at a common, everyday form of a food vs. an unusual or
# heavily processed one. Used only as a gentle tiebreak so generic searches
# ("egg") surface the everyday form ("Egg, whole, ...") instead of a rarity
# like "Egg, yolk, dried". Deliberately small and hand-tuned.
_COMMON_GOOD = (
    "raw", "cooked", "fresh", "whole", "roasted", "boiled", "baked",
    "grilled", "steamed", "broiled", "fried", "scrambled", "poached", "omelet",
)
_COMMON_BAD = (
    "dried", "dehydrated", "powder", "freeze", "canned", "frozen", "pickled",
    "brined", "cured", "smoked", "concentrate", "syrup", "jerky", "cand",
    "imitation", "substitute", "babyfood", "infant", "formula", "restaurant",
    "nfs", "drained", "solids", "fortified", "unenriched", "leavening",
    "shortening", "without", "roll", "deli", "sliced", "tenders", "breaded",
    "prepackaged", "flavored", "seasoned", "meatless", "variety", "by-product",
    "feet", "giblet", "gizzard", "neck", "brain", "tripe",
)
_WORD_RE = re.compile(r"[a-z0-9]+")
_ACRO_RE = re.compile(r"[A-Z]{3,}")


def commonness(name):
    """0-centered score of how everyday a food form is (higher = more common)."""
    lower = name.lower()
    toks = _WORD_RE.findall(lower)
    parts = name.split(",")
    s = -(len(parts) - 1) * 2.0
    for w in _COMMON_GOOD:
        if any(t == w or t.startswith(w) for t in toks):
            s += 3
    for w in _COMMON_BAD:
        if any(t == w or t.startswith(w) for t in toks):
            s -= 5
    if "includes" in lower:
        s -= 5
    for tok in _ACRO_RE.findall(name):
        if tok != "USDA":
            s -= 8
    return max(-30.0, min(16.0, s))


def to_slug(name):
    slug = name.lower()
    slug = slug.replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def parse_sr(path):
    """Return list of field lists from a ^-delimited, ~-quoted ASCII file."""
    rows = []
    with open(path, encoding="latin-1", newline="") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line:
                continue
            fields = [f.strip("~") for f in line.split("^")]
            rows.append(fields)
    return rows


def clean_name(name):
    """Normalize a USDA description to a clean display title."""
    if not name:
        return name
    parts = [p.strip() for p in name.split(",")]
    return ", ".join(parts)


def fmt(num, places=0):
    if num is None:
        return "&ndash;"
    return f"{num:.{places}f}"


class Food:
    __slots__ = ("ndb", "group_code", "name", "slug", "nutrients",
                 "servings", "rank")

    def __init__(self, ndb, group_code, name):
        self.ndb = ndb
        self.group_code = group_code
        self.name = clean_name(name)
        self.slug = ""
        self.nutrients = {}
        self.servings = []
        self.rank = 0

    @property
    def kcal(self):
        return self.nutrients.get("208")

    @property
    def url(self):
        return f"/food/{self.slug}/"


def build(paths, top=0, curated=False):
    foods = {}
    groups = {}

    for row in parse_sr(paths["group"]):
        if len(row) >= 2:
            groups[row[0]] = row[1]

    for row in parse_sr(paths["food"]):
        if len(row) < 3:
            continue
        ndb, gcode, ldesc = row[0], row[1], row[2]
        if not ldesc:
            continue
        foods[ndb] = Food(ndb, gcode, ldesc)

    for row in parse_sr(paths["nutdata"]):
        if len(row) < 3:
            continue
        ndb, nno, val = row[0], row[1], row[2]
        food = foods.get(ndb)
        if food is None:
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        if nno in NUTRIENTS:
            food.nutrients[nno] = v

    for row in parse_sr(paths["weight"]):
        if len(row) < 5:
            continue
        ndb, seq, amt, mdesc, g = row[0], row[1], row[2], row[3], row[4]
        food = foods.get(ndb)
        if food is None:
            continue
        try:
            grams = float(g)
            amount = float(amt) if amt else 1.0
        except ValueError:
            continue
        if grams <= 0 or not mdesc:
            continue
        food.servings.append((amount, mdesc, grams))

    # Keep only foods with calorie data
    valid = [f for f in foods.values() if f.kcal is not None and f.kcal > 0]

    # Popularity rank from POPULAR_TERMS
    for f in valid:
        lower = f.name.lower()
        score = 0
        for term in POPULAR_TERMS:
            if term in lower:
                score += 1
        f.rank = score

    if curated:
        # Launch set: for each curated high-demand term, find the best matching
        # food and let it own the clean '/food/<term>/' URL.
        picked = []
        seen_ndb = set()
        for term in CURATED_BASES:
            term_l = term.lower()
            cands = [f for f in valid
                     if term_l in f.name.lower()
                     and f.ndb not in seen_ndb]
            if not cands:
                continue
            primary = pick_primary(cands)
            primary.slug = to_slug(term)
            if not primary.slug:
                primary.slug = f"food-{primary.ndb}"
            seen_ndb.add(primary.ndb)
            picked.append(primary)
        valid = picked
        # Ensure unique slugs across the picked set
        seen = {}
        for f in valid:
            s = f.slug
            if s in seen:
                seen[s] += 1
                f.slug = f"{s}-{seen[s]}"
            else:
                seen[s] = 1
    elif top:
        ranked = sorted(valid, key=lambda f: (-f.rank, f.name))
        ranked = [f for f in ranked if f.rank > 0]
        valid = ranked[:top]

    if not curated:
        # Assign unique slugs. The primary variant of a base owns the clean
        # '/food/<base>/' URL; other variants get a short qualifier appended.
        by_base = {}
        for f in valid:
            by_base.setdefault(primary_key(f.name), []).append(f)

        seen = {}
        for base, variants in by_base.items():
            primary = pick_primary(variants)
            if primary.slug:
                base_slug = primary.slug
            else:
                base_slug = to_slug(base)
            if not base_slug:
                base_slug = f"food-{primary.ndb}"
            if base_slug not in seen:
                seen[base_slug] = 1
                primary.slug = base_slug
            else:
                # base name already owned by another food; force a suffix
                seen[base_slug] += 1
                primary.slug = f"{base_slug}-{seen[base_slug]}"
            for f in variants:
                if f is primary:
                    continue
                qual = f.name.split(",", 1)[1].strip() if "," in f.name else ""
                qual_slug = to_slug(qual)
                if qual_slug and qual_slug != base_slug:
                    cand = f"{base_slug}-{qual_slug}"
                else:
                    cand = f"{base_slug}-{f.ndb}"
                n = 1
                while cand in seen:
                    n += 1
                    cand = f"{cand}-{n}"
                seen[cand] = 1
                f.slug = cand

    by_group = {}
    for f in valid:
        by_group.setdefault(f.group_code, []).append(f)

    return groups, valid, by_group


def render_food(food, groups, by_group, all_sorted):
    esc = escape
    kcal = food.kcal
    per100 = {n: food.nutrients.get(n) for n in NUTRIENTS}
    rows = []
    for nno, (label, unit) in NUTRIENTS.items():
        v = per100[nno]
        rows.append((label, fmt(v, 2 if unit in ("g", "mg") else 0), unit))

    # per-serving table
    serving_rows = []
    for amount, mdesc, grams in food.servings:
        cals = kcal * grams / 100.0
        serving_rows.append((fmt(amount, 1 if amount % 1 else 0), mdesc, fmt(grams, 1), round(cals)))

    related = [x for x in by_group.get(food.group_code, []) if x.ndb != food.ndb]
    related.sort(key=lambda x: -x.rank)
    related = related[:8]

    breadcrumb = [
        {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": BASE_URL},
        {"@type": "ListItem", "position": 2,
         "name": groups.get(food.group_code, "Foods"),
         "item": BASE_URL + f"/category/{to_slug(groups.get(food.group_code, ''))}/"},
        {"@type": "ListItem", "position": 3, "name": f"Calories in {food.name}",
         "item": BASE_URL + food.url},
    ]
    nutrition_schema = {
        "@context": "https://schema.org",
        "@type": "NutritionInformation",
        "servingSize": "100 g",
        "calories": f"{kcal:.0f} kcal",
        "proteinContent": f"{fmt(per100['203'], 1)} g",
        "fatContent": f"{fmt(per100['204'], 1)} g",
        "carbohydrateContent": f"{fmt(per100['205'], 1)} g",
    }
    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": breadcrumb,
    }

    faq = [
        ("How many calories are in {name}?",
         "{name} contains about {kcal:.0f} calories per 100 grams (about {oz:.0f} calories per ounce)."),
        ("What is the serving size for {name}?",
         "100 grams of {name} is a common reference serving. "
         + ("{name} also has standard household measures listed in the serving table above." if food.servings else "USDA reports values per 100 g.")),
        ("Is {name} high in calories?",
         ("Yes" if kcal > 300 else "Moderate" if kcal > 100 else "No") + f" — at {kcal:.0f} kcal per 100 g, "
         + ("it is calorie-dense compared with most foods." if kcal > 300 else "it is a relatively low-calorie food.")),
    ]

    title = f"Calories in {food.name} &ndash; Per 100 g &amp; Serving Size | {SITE_NAME}"
    desc = f"How many calories are in {food.name}? Find nutrition facts for {food.name}: calories, protein, carbs, fat, fiber and more per 100 g, plus common serving sizes."
    canonical = BASE_URL + food.url

    related_html = "".join(
        f'<li><a href="{x.url}">Calories in {esc(x.name)}</a>'
        f' <span class="muted">({x.kcal:.0f} kcal/100g)</span></li>'
        for x in related
    ) or "<li>No related foods yet.</li>"

    faq_html = ""
    for q, a in faq:
        qtxt = q.format(name=food.name)
        atxt = a.format(name=food.name, kcal=kcal, oz=round(kcal / 28.35))
        faq_html += f'<details class="faq"><summary>{esc(qtxt)}</summary><p>{esc(atxt)}</p></details>\n'

    nutrition_html = "".join(
        f"<tr><td>{esc(label)}</td><td class='num'>{v}</td><td class='num'>{esc(unit)}</td></tr>"
        for label, v, unit in rows
    )
    servings_html = "".join(
        f"<tr><td class='num'>{amt}</td><td>{esc(md)}</td><td class='num'>{g} g</td><td class='num'>{c} kcal</td></tr>"
        for amt, md, g, c in serving_rows
    ) or "<tr><td colspan='4' class='muted'>Standard serving measures not available.</td></tr>"

    category_url = f"/category/{to_slug(groups.get(food.group_code, 'foods'))}/"
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="Calories in {esc(food.name)}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="article">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{json.dumps(nutrition_schema)}</script>
<script type="application/ld+json">{json.dumps(breadcrumb_schema)}</script>
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="/">{SITE_NAME}</a>
    <nav aria-label="Main"><a href="/">Home</a> · <a href="/popular/">Popular foods</a></nav>
  </div>
</header>
<main class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a> &raquo; <a href="{category_url}">{esc(groups.get(food.group_code, 'Foods'))}</a> &raquo; <span>{esc(food.name)}</span></nav>
<h1>Calories in {esc(food.name)}</h1>
<p class="lead">{esc(food.name)} nutrition facts. Data from the <a href="https://fdc.nal.usda.gov/" rel="nofollow noopener">USDA FoodData Central</a>, SR Legacy database.</p>

<section class="card" aria-label="Nutrition facts">
  <h2>Nutrition facts per 100 g</h2>
  <table class="nut">
    <thead><tr><th>Nutrient</th><th>Amount</th><th>Unit</th></tr></thead>
    <tbody>{nutrition_html}</tbody>
  </table>
  <p class="muted small">Values are per 100 grams as reported in the USDA SR Legacy database (food ID {esc(food.ndb)}).</p>
</section>

<section class="card" aria-label="Serving sizes">
  <h2>Calories in common servings of {esc(food.name)}</h2>
  <table class="serv">
    <thead><tr><th>Measure</th><th>Serving</th><th>Weight</th><th>Calories</th></tr></thead>
    <tbody>{servings_html}</tbody>
  </table>
</section>

<section class="card" aria-label="Questions">
  <h2>Frequently asked questions</h2>
  {faq_html}
</section>

<section class="card" aria-label="Related foods">
  <h2>Related foods</h2>
  <ul class="related">{related_html}</ul>
</section>
</main>
<footer class="site-footer">
  <div class="wrap">
    <p>{SITE_NAME} — {SITE_TAGLINE}.</p>
    <p class="muted small">Nutrition data: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy. Public domain.</p>
  </div>
</footer>
</body>
</html>
"""
    return page, canonical


def render_category(gcode, gname, foods):
    esc = escape
    slug = to_slug(gname)
    items = sorted(foods, key=lambda f: (not f.name[0].isalpha(), f.name.lower()))
    lis = "".join(
        f'<li><a href="{f.url}">Calories in {esc(f.name)}</a> <span class="muted">({f.kcal:.0f} kcal/100g)</span></li>'
        for f in items
    )
    title = f"Calories in {esc(gname)} &ndash; Full List | {SITE_NAME}"
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="Complete list of foods in the {esc(gname)} group with calories and nutrition per 100 g, from the USDA SR Legacy database.">
<link rel="canonical" href="{BASE_URL}/category/{slug}/">
<meta name="robots" content="index, follow">
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<header class="site-header"><div class="wrap"><a class="brand" href="/">{SITE_NAME}</a><nav><a href="/">Home</a> · <a href="/popular/">Popular foods</a> · <a href="/tracker/">Tracker</a></nav></div></header>
<main class="wrap">
<nav class="crumbs"><a href="/">Home</a> &raquo; <span>{esc(gname)}</span></nav>
<h1>Calories in {esc(gname)} foods</h1>
<p class="lead">{len(items)} foods in this category with calorie counts per 100 g, from the USDA SR Legacy database.</p>
<ul class="food-list">{lis}</ul>
</main>
<footer class="site-footer"><div class="wrap"><p>{SITE_NAME} &mdash; {SITE_TAGLINE}.</p></div></footer>
</body>
</html>
"""
    return page


def render_home(groups, by_group, popular):
    esc = escape
    cards = []
    for gcode in sorted(by_group, key=lambda c: groups.get(c, "")):
        gname = groups.get(gcode, "Foods")
        count = len(by_group[gcode])
        cards.append(
            f'<a class="cat" href="/category/{to_slug(gname)}/"><span class="cat-name">{esc(gname)}</span><span class="muted">{count} foods</span></a>'
        )
    pop_items = popular[:30]
    pop_html = "".join(
        f'<li><a href="{f.url}">Calories in {esc(f.name)}</a> <span class="muted">({f.kcal:.0f} kcal)</span></li>'
        for f in pop_items
    )
    website_schema = json.dumps({"@context": "https://schema.org",
                                 "@type": "WebSite", "name": SITE_NAME, "url": BASE_URL})
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SITE_NAME} &ndash; {SITE_TAGLINE}</title>
<meta name="description" content="Look up calories and nutrition facts for {len([f for g in by_group.values() for f in g])} foods. Per-100g data and serving sizes from the USDA SR Legacy database.">
<link rel="canonical" href="{BASE_URL}/">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{website_schema}</script>
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<header class="site-header"><div class="wrap"><a class="brand" href="/">{SITE_NAME}</a><nav><a href="/">Home</a> · <a href="/popular/">Popular foods</a> · <a href="/tracker/">Tracker</a></nav></div></header>
<main class="wrap">
<h1>{SITE_NAME}</h1>
<p class="lead">{SITE_TAGLINE}. Every food page shows calories, protein, carbs, fat, fiber and sugar per 100 g, plus common serving sizes.</p>
<section class="card cta">
  <h2>Track your calories &amp; macros</h2>
  <p class="lead" style="margin:0 0 14px">Use the free Calorie &amp; Macro Tracker to log what you eat and see calories, protein, carbs and fat against your goals. It runs in your browser, works on your phone, and saves your log automatically &mdash; no account needed.</p>
  <p style="margin:0"><a class="btn" href="/tracker/">Open the Tracker &rarr;</a></p>
</section>
<section class="card">
  <h2>Browse by category</h2>
  <div class="cats">{''.join(cards)}</div>
</section>
<section class="card">
  <h2>Most searched foods</h2>
  <ul class="food-list">{pop_html}</ul>
</section>
</main>
<footer class="site-footer"><div class="wrap"><p>{SITE_NAME} &mdash; {SITE_TAGLINE}.</p></div></footer>
</body>
</html>
"""
    return page


def render_popular(popular):
    esc = escape
    lis = "".join(
        f'<li><a href="{f.url}">Calories in {esc(f.name)}</a> <span class="muted">({f.kcal:.0f} kcal/100g)</span></li>'
        for f in popular
    )
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Popular Foods &ndash; {SITE_NAME}</title>
<meta name="description" content="Most searched foods on {SITE_NAME} with calories per 100 g.">
<link rel="canonical" href="{BASE_URL}/popular/">
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<header class="site-header"><div class="wrap"><a class="brand" href="/">{SITE_NAME}</a><nav><a href="/">Home</a> · <a href="/popular/">Popular foods</a> · <a href="/tracker/">Tracker</a></nav></div></header>
<main class="wrap">
<nav class="crumbs"><a href="/">Home</a> &raquo; <span>Popular foods</span></nav>
<h1>Popular foods</h1>
<p class="lead">The most searched foods on {SITE_NAME}.</p>
<ul class="food-list">{lis}</ul>
</main>
<footer class="site-footer"><div class="wrap"><p>{SITE_NAME} &mdash; {SITE_TAGLINE}.</p></div></footer>
</body>
</html>
"""
    return page


CSS = """\
:root{--accent:#1a7f37;--ink:#1f2328;--muted:#6e7781;--line:#d0d7de;--bg:#f6f8fa}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg);line-height:1.55}
.wrap{max-width:880px;margin:0 auto;padding:0 16px}
.site-header{background:#fff;border-bottom:1px solid var(--line);padding:14px 0}
.site-header .wrap{display:flex;align-items:center;justify-content:space-between}
.brand{font-weight:700;font-size:18px;color:var(--ink);text-decoration:none}
nav a{color:var(--muted);text-decoration:none;font-size:14px}
nav a:hover{color:var(--accent)}
.crumbs{font-size:13px;color:var(--muted);margin:18px 0 4px}
h1{font-size:28px;margin:8px 0 6px}
h2{font-size:19px;margin:0 0 10px}
.lead{color:var(--muted);margin:0 0 20px}
.card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px 20px;margin:0 0 18px}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}
th{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.muted{color:var(--muted)}.small{font-size:13px}
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.cat{display:block;border:1px solid var(--line);border-radius:8px;padding:10px 12px;text-decoration:none;color:var(--ink);background:#fff}
.cat:hover{border-color:var(--accent)}
.cat-name{display:block;font-weight:600}
.card.cta{border-color:var(--accent);background:linear-gradient(180deg,#f2fbf4,#fff)}
.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;font-weight:600;padding:10px 18px;border-radius:8px}
.btn:hover{filter:brightness(1.06)}
.food-list{columns:2;column-gap:36px;margin:0;padding-left:20px;font-size:15px}
.food-list li{margin:0 0 6px;break-inside:avoid}
.related{columns:2;column-gap:36px;margin:0;padding-left:20px;font-size:15px}
.related li{margin:0 0 6px;break-inside:avoid}
details.faq{border:1px solid var(--line);border-radius:6px;margin:0 0 8px;padding:8px 12px;background:#fff}
details.faq summary{cursor:pointer;font-weight:600}
details.faq p{margin:8px 0 2px;color:var(--ink)}
.site-footer{border-top:1px solid var(--line);background:#fff;margin-top:28px;padding:18px 0;font-size:14px}
@media(max-width:560px){.food-list,.related{columns:1}nav{display:none}}
"""


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=0,
                    help="only build the top N ranked popular foods (0 = all)")
    ap.add_argument("--curated", action="store_true",
                    help="build the curated high-demand launch set")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "out"))
    ap.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "..", "data", "sr"))
    args = ap.parse_args()

    data = args.data
    paths = {
        "group": os.path.join(data, "FD_GROUP.txt"),
        "food": os.path.join(data, "FOOD_DES.txt"),
        "nutdata": os.path.join(data, "NUT_DATA.txt"),
        "nutdef": os.path.join(data, "NUTR_DEF.txt"),
        "weight": os.path.join(data, "WEIGHT.txt"),
    }
    for p in paths.values():
        if not os.path.exists(p):
            print(f"Missing data file: {p}", file=sys.stderr)
            sys.exit(1)

    groups, foods, by_group = build(paths, top=args.top, curated=args.curated)
    out = os.path.abspath(args.out)
    if os.path.isdir(out):
        for entry in os.listdir(out):
            ep = os.path.join(out, entry)
            if os.path.isdir(ep) and not os.path.islink(ep):
                shutil.rmtree(ep)
            else:
                os.remove(ep)
    os.makedirs(out, exist_ok=True)

    popular = sorted([f for f in foods if f.rank > 0], key=lambda x: (-x.rank, x.name))

    write_file(os.path.join(out, "styles.css"), CSS)
    write_file(os.path.join(out, "index.html"), render_home(groups, by_group, popular))
    write_file(os.path.join(out, "popular", "index.html"), render_popular(popular))

    # Cloudflare Pages headers: strong caching for assets, noindex on staging
    headers = (
        "/*\n"
        "  X-Robots-Tag: index, follow\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  X-Frame-Options: SAMEORIGIN\n"
        "\n"
        "/styles.css\n"
        "  Cache-Control: public, max-age=86400\n"
        "/foods.json\n"
        "  Cache-Control: public, max-age=3600\n"
    )
    write_file(os.path.join(out, "_headers"), headers)
    write_file(os.path.join(out, "google61a0cf73666fd148.html"), "google-site-verification: google61a0cf73666fd148.html")

    sitemap = []
    sitemap.append(("0.9", BASE_URL + "/"))
    sitemap.append(("0.8", BASE_URL + "/tracker/"))
    sitemap.append(("0.6", BASE_URL + "/popular/"))

    cat_slugs = {}
    for gcode, flist in by_group.items():
        gname = groups.get(gcode, "Foods")
        slug = to_slug(gname)
        if slug in cat_slugs:
            slug += f"-{gcode}"
        cat_slugs[slug] = gcode
        write_file(os.path.join(out, "category", slug, "index.html"),
                   render_category(gcode, gname, flist))
        sitemap.append(("0.6", BASE_URL + f"/category/{slug}/"))

    for f in foods:
        page, canonical = render_food(f, groups, by_group, foods)
        write_file(os.path.join(out, "food", f.slug, "index.html"), page)
        sitemap.append(("0.5", canonical))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for prio, loc in sitemap:
        lines.append(f"  <url><loc>{loc}</loc><priority>{prio}</priority></url>")
    lines.append("</urlset>")
    write_file(os.path.join(out, "sitemap.xml"), "\n".join(lines) + "\n")

    robots = f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n"
    write_file(os.path.join(out, "robots.txt"), robots)

    # Search index + per-100g macros + common servings. Used by the homepage
    # search box AND the /tracker/ web app. Kept compact (no whitespace).
    index = []
    for food in foods:
        nut = food.nutrients
        item = {
            "n": food.name,
            "u": food.url,
            "c": groups.get(food.group_code, ""),
            "k": round(food.kcal, 1),
            "pop": round(commonness(food.name), 1),
        }
        for key, nno in (("p", "203"), ("cb", "205"), ("f", "204")):
            val = nut.get(nno)
            item[key] = round(val, 1) if val is not None else None
        servings = []
        for _amt, desc, grams in food.servings:
            if desc and grams and grams > 0:
                servings.append({"d": desc, "g": round(grams, 1)})
            if len(servings) >= 3:
                break
        if servings:
            item["sv"] = servings
        index.append(item)
    write_file(os.path.join(out, "foods.json"),
               json.dumps(index, separators=(",", ":")))

    # Static tracking web app. Files live in templates/tracker and are copied
    # into /tracker/ on every build (out/ is wiped at the start of each build).
    tracker_src = os.path.join(os.path.dirname(__file__), "..", "templates", "tracker")
    if os.path.isdir(tracker_src):
        tracker_dst = os.path.join(out, "tracker")
        os.makedirs(tracker_dst, exist_ok=True)
        for name in os.listdir(tracker_src):
            src_path = os.path.join(tracker_src, name)
            if os.path.isfile(src_path):
                shutil.copyfile(src_path, os.path.join(tracker_dst, name))
        print(f"Copied tracker app -> {tracker_dst}")

    print(f"Built {len(foods)} food pages, {len(by_group)} categories -> {out}")
    print(f"Total foods with calorie data available: {len(foods)}")


if __name__ == "__main__":
    main()
