CREATE TABLE "user" (
  "user_id" integer PRIMARY KEY,
  "username" varchar(255) UNIQUE NOT NULL,
  "full_name" varchar(255) NOT NULL,
  "email" varchar(255) NOT NULL,
  "gender" varchar(1) NOT NULL,
  "date_of_birth" date,
  "date_joined" timestamp NOT NULL DEFAULT (now())
);

CREATE TABLE "exercises" (
  "exercise_id" integer PRIMARY KEY,
  "exercise_name" varchar(100),
  "description" text,
  "type" varchar(20),
  "difficulty" varchar(6) NOT NULL,
  "equipment" varchar(20) NOT NULL
);

CREATE TABLE "muscles" (
  "muscle_id" integer PRIMARY KEY,
  "muscle_name" varchar(100) NOT NULL
);

CREATE TABLE "muscles_exercised" (
  "exercise_id" integer,
  "muscle_id" integer,
  "role" varchar(10) NOT NULL,
  PRIMARY KEY ("exercise_id", "muscle_id")
);

CREATE TABLE "injuries" (
  "injury_id" integer PRIMARY KEY,
  "user_id" integer,
  "location" varchar(20),
  "severity" varchar(6),
  "occurance" timestamp DEFAULT (now()),
  "status" varchar(20)
);

CREATE TABLE "plans" (
  "plan_id" integer PRIMARY KEY,
  "plan_name" varchar(255),
  "user_id" integer
);

CREATE TABLE "plan_exercises" (
  "plan_id" integer,
  "exercise_id" integer,
  "order" integer,
  "sets" integer,
  "reps" integer,
  PRIMARY KEY ("plan_id", "exercise_id")
);

-- Nutrition reference data: CoFID 2021 (McCance & Widdowson's Composition of Foods).
-- All values are per 100g of food, except alcoholic beverages which are per 100ml.
-- CoFID sentinels are resolved on import: Tr (trace) -> 0, N/blank (unmeasured) -> NULL.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE "foods" (
  "id"             serial PRIMARY KEY,
  "food_code"      varchar(10) NOT NULL,      -- CoFID code, e.g. '13-145'; NOT unique:
                                              -- the source has a duplicate (13-669)
  "food_name"      varchar(255) NOT NULL,
  "description"    text,
  "food_group"     varchar(4),                -- CoFID group code, e.g. 'DG'
  "kcal"           real,
  "protein_g"      real,
  "fat_g"          real,
  "carb_g"         real,
  "total_sugars_g" real,
  "fibre_nsp_g"    real,                       -- Non-starch polysaccharide (Englyst)
  "fibre_aoac_g"   real,                       -- AOAC fibre
  "embedding"      vector(768)                 -- nomic-embed-text
);
CREATE INDEX ON "foods" ("food_code");

-- UK dietary guideline values, from PHE "Government Dietary Recommendations"
-- (2016), Tables 1 & 2 (macronutrients). Energy = EAR (SACN 2011); protein =
-- RNI (COMA 1991); the rest are population targets. Look up a user's row with:
--   WHERE sex = <user.gender> AND <age> BETWEEN age_min AND age_max
CREATE TABLE "nutrient_reference" (
  "id"         serial PRIMARY KEY,
  "sex"        varchar(1) NOT NULL,       -- 'M' / 'F' (matches "user".gender)
  "age_min"    integer NOT NULL,
  "age_max"    integer NOT NULL,          -- 200 = open-ended (75+)
  "nutrient"   varchar(20) NOT NULL,      -- energy_kcal, protein_g, fat_g, satfat_g, carb_g, free_sugars_g, fibre_g
  "value"      real NOT NULL,
  "limit_type" varchar(6) NOT NULL        -- 'target' | 'min' (at least) | 'max' (less than)
);
CREATE INDEX ON "nutrient_reference" ("sex", "age_min", "age_max");

COMMENT ON COLUMN "exercises"."description" IS 'Description of the exercise';

ALTER TABLE "muscles_exercised" ADD FOREIGN KEY ("exercise_id") REFERENCES "exercises" ("exercise_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "muscles_exercised" ADD FOREIGN KEY ("muscle_id") REFERENCES "muscles" ("muscle_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "injuries" ADD FOREIGN KEY ("user_id") REFERENCES "user" ("user_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "plan_exercises" ADD FOREIGN KEY ("plan_id") REFERENCES "plans" ("plan_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "plan_exercises" ADD FOREIGN KEY ("exercise_id") REFERENCES "exercises" ("exercise_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "plans" ADD FOREIGN KEY ("user_id") REFERENCES "user" ("user_id") DEFERRABLE INITIALLY IMMEDIATE;
