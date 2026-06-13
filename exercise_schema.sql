CREATE TABLE "user" (
  "user_id" integer PRIMARY KEY,
  "username" varchar(255) UNIQUE NOT NULL,
  "full_name" varchar(255) NOT NULL,
  "email" varchar(255) NOT NULL,
  "gender" varchar(1) NOT NULL,
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

COMMENT ON COLUMN "exercises"."description" IS 'Description of the exercise';

ALTER TABLE "muscles_exercised" ADD FOREIGN KEY ("exercise_id") REFERENCES "exercises" ("exercise_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "muscles_exercised" ADD FOREIGN KEY ("muscle_id") REFERENCES "muscles" ("muscle_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "injuries" ADD FOREIGN KEY ("user_id") REFERENCES "user" ("user_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "plan_exercises" ADD FOREIGN KEY ("plan_id") REFERENCES "plans" ("plan_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "plan_exercises" ADD FOREIGN KEY ("exercise_id") REFERENCES "exercises" ("exercise_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "plans" ADD FOREIGN KEY ("user_id") REFERENCES "user" ("user_id") DEFERRABLE INITIALLY IMMEDIATE;
