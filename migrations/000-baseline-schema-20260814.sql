--
-- PostgreSQL database dump
--

\restrict VP8UaTSvRMDL6ihCFXrHZu06P59CDSPHRfRJiyRfLYPPLhWkLaopgAPUYuqu79I

-- Dumped from database version 18.4 (Debian 18.4-1.pgdg13+1)
-- Dumped by pg_dump version 18.4 (Debian 18.4-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: maya_rp; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA maya_rp;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _migrations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp._migrations (
    id integer NOT NULL,
    name text,
    applied_at timestamp with time zone DEFAULT now()
);


--
-- Name: _migrations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp._migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: _migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp._migrations_id_seq OWNED BY maya_rp._migrations.id;


--
-- Name: academy_campuses; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.academy_campuses (
    id integer NOT NULL,
    name text,
    colony_id integer,
    student_slots_used integer DEFAULT 0,
    max_students integer DEFAULT 10,
    prestige integer DEFAULT 0,
    level integer DEFAULT 1
);


--
-- Name: academy_campuses_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.academy_campuses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: academy_campuses_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.academy_campuses_id_seq OWNED BY maya_rp.academy_campuses.id;


--
-- Name: active_disasters; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.active_disasters (
    id integer NOT NULL,
    session_id integer,
    template_id integer,
    sector_id integer,
    name character varying(100),
    tick_started integer NOT NULL,
    ticks_remaining integer NOT NULL,
    severity integer NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying,
    effects_applied jsonb DEFAULT '[]'::jsonb
);


--
-- Name: active_disasters_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.active_disasters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: active_disasters_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.active_disasters_id_seq OWNED BY maya_rp.active_disasters.id;


--
-- Name: active_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.active_events (
    id integer NOT NULL,
    template_id integer,
    territory_id integer,
    started_at timestamp without time zone DEFAULT now(),
    resolved boolean DEFAULT false,
    resolved_at timestamp without time zone,
    resolution text
);


--
-- Name: active_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.active_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: active_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.active_events_id_seq OWNED BY maya_rp.active_events.id;


--
-- Name: active_scenes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.active_scenes (
    id integer NOT NULL,
    session_id integer,
    scene_type text NOT NULL,
    character_involved text,
    context_json jsonb DEFAULT '{}'::jsonb,
    started_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone DEFAULT (now() + '00:30:00'::interval)
);


--
-- Name: active_scenes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.active_scenes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: active_scenes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.active_scenes_id_seq OWNED BY maya_rp.active_scenes.id;


--
-- Name: adjutant_prompts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.adjutant_prompts (
    id integer NOT NULL,
    session_id integer NOT NULL,
    ministry text NOT NULL,
    holder text NOT NULL,
    action text NOT NULL,
    target text,
    impact text,
    urgency text DEFAULT 'normal'::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    routed_via text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    resolved_at timestamp with time zone
);


--
-- Name: adjutant_prompts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.adjutant_prompts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: adjutant_prompts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.adjutant_prompts_id_seq OWNED BY maya_rp.adjutant_prompts.id;


--
-- Name: ai_decision_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ai_decision_log (
    id integer NOT NULL,
    session_id integer,
    faction_name character varying(100) NOT NULL,
    tick_number integer NOT NULL,
    decision_type character varying(50) NOT NULL,
    rationale text,
    outcome jsonb DEFAULT '{}'::jsonb
);


--
-- Name: ai_decision_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ai_decision_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_decision_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ai_decision_log_id_seq OWNED BY maya_rp.ai_decision_log.id;


--
-- Name: ai_decisions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ai_decisions (
    id integer NOT NULL,
    faction_id integer,
    decision_type character varying(50),
    target_faction_id integer,
    details jsonb,
    made_at timestamp without time zone DEFAULT now(),
    executed boolean DEFAULT false
);


--
-- Name: ai_decisions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ai_decisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_decisions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ai_decisions_id_seq OWNED BY maya_rp.ai_decisions.id;


--
-- Name: ai_tactics_history; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ai_tactics_history (
    id integer NOT NULL,
    faction_id integer,
    player_faction_id integer,
    tactic_used character varying(50),
    count integer DEFAULT 1,
    last_used timestamp without time zone,
    win_rate numeric DEFAULT 0.5
);


--
-- Name: ai_tactics_history_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ai_tactics_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_tactics_history_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ai_tactics_history_id_seq OWNED BY maya_rp.ai_tactics_history.id;


--
-- Name: alchemy_recipes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.alchemy_recipes (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    inputs jsonb DEFAULT '{}'::jsonb NOT NULL,
    outputs jsonb DEFAULT '{}'::jsonb NOT NULL,
    catalyst character varying(100),
    success_rate double precision DEFAULT 0.7,
    tech_tier integer DEFAULT 3,
    lore_text text
);


--
-- Name: alchemy_recipes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.alchemy_recipes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alchemy_recipes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.alchemy_recipes_id_seq OWNED BY maya_rp.alchemy_recipes.id;


--
-- Name: alert_queue; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.alert_queue (
    id integer NOT NULL,
    session_id integer NOT NULL,
    alert_type text NOT NULL,
    title text NOT NULL,
    description text,
    priority integer DEFAULT 0,
    read boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT alert_queue_alert_type_check CHECK ((alert_type = ANY (ARRAY['raid'::text, 'siege'::text, 'quest'::text, 'horror'::text, 'trade'::text, 'diplomacy'::text, 'construction'::text, 'research'::text, 'crew'::text, 'intimacy'::text, 'dark'::text, 'system'::text]))),
    CONSTRAINT alert_queue_priority_check CHECK (((priority >= 0) AND (priority <= 10)))
);


--
-- Name: alert_queue_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.alert_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alert_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.alert_queue_id_seq OWNED BY maya_rp.alert_queue.id;


--
-- Name: animal_encounters; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.animal_encounters (
    id integer NOT NULL,
    session_id integer,
    animal_id integer,
    system_id integer,
    status character varying(20) DEFAULT 'active'::character varying,
    encountered_at timestamp without time zone DEFAULT now(),
    resolved_at timestamp without time zone,
    outcome character varying(50)
);


--
-- Name: animal_encounters_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.animal_encounters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: animal_encounters_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.animal_encounters_id_seq OWNED BY maya_rp.animal_encounters.id;


--
-- Name: anomalies_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.anomalies_catalog (
    id integer NOT NULL,
    session_id integer,
    sector_id integer,
    anomaly_type character varying(50),
    name character varying(200),
    description text,
    studied boolean DEFAULT false,
    data_collected integer DEFAULT 0,
    data_threshold integer DEFAULT 100,
    discovery_reward jsonb DEFAULT '{}'::jsonb,
    discovered_at timestamp with time zone
);


--
-- Name: anomalies_catalog_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.anomalies_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: anomalies_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.anomalies_catalog_id_seq OWNED BY maya_rp.anomalies_catalog.id;


--
-- Name: anti_cloak_grids; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.anti_cloak_grids (
    id integer NOT NULL,
    session_id integer NOT NULL,
    system_name text NOT NULL,
    level integer DEFAULT 1,
    detection_pct integer DEFAULT 15,
    range_ly integer DEFAULT 3,
    upkeep_credits integer DEFAULT 200,
    status text DEFAULT 'active'::text,
    built_at timestamp with time zone DEFAULT now(),
    territory_id integer,
    CONSTRAINT anti_cloak_grids_level_check CHECK (((level >= 1) AND (level <= 5)))
);


--
-- Name: anti_cloak_grids_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.anti_cloak_grids_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: anti_cloak_grids_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.anti_cloak_grids_id_seq OWNED BY maya_rp.anti_cloak_grids.id;


--
-- Name: artifact_history; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.artifact_history (
    id integer NOT NULL,
    artifact_id integer,
    action character varying(100) NOT NULL,
    tick_number integer,
    actor character varying(100),
    from_location character varying(200),
    to_location character varying(200),
    happened_at timestamp with time zone DEFAULT now(),
    from_territory_id integer,
    to_territory_id integer
);


--
-- Name: artifact_history_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.artifact_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: artifact_history_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.artifact_history_id_seq OWNED BY maya_rp.artifact_history.id;


--
-- Name: artifacts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.artifacts (
    id integer NOT NULL,
    session_id integer,
    name text,
    type text,
    rarity text DEFAULT 'common'::text,
    description text,
    bonus integer DEFAULT 0,
    curse text,
    equipped_to integer,
    created_at timestamp with time zone DEFAULT now(),
    sacrifice_backstory text,
    award_recipient text
);


--
-- Name: artifacts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.artifacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: artifacts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.artifacts_id_seq OWNED BY maya_rp.artifacts.id;


--
-- Name: auto_queue; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.auto_queue (
    id integer NOT NULL,
    session_id integer NOT NULL,
    yard text DEFAULT 'Heaven'::text NOT NULL,
    ship_type text NOT NULL,
    hull_class text DEFAULT 'support'::text NOT NULL,
    quota integer DEFAULT 1 NOT NULL,
    ship_name_prefix text NOT NULL,
    alloy_cost bigint DEFAULT 0 NOT NULL,
    fuel_cost bigint DEFAULT 0 NOT NULL,
    credit_cost bigint DEFAULT 0 NOT NULL,
    build_time_hours integer DEFAULT 24 NOT NULL,
    priority integer DEFAULT 1 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: auto_queue_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.auto_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auto_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.auto_queue_id_seq OWNED BY maya_rp.auto_queue.id;


--
-- Name: battle_terrain; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.battle_terrain (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    effects jsonb,
    rarity character varying(20) DEFAULT 'common'::character varying
);


--
-- Name: battle_terrain_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.battle_terrain_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: battle_terrain_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.battle_terrain_id_seq OWNED BY maya_rp.battle_terrain.id;


--
-- Name: bug_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.bug_events (
    id integer NOT NULL,
    session_id integer,
    infestation_id integer,
    event_type character varying(50),
    description text,
    severity integer DEFAULT 1,
    happened_at timestamp without time zone DEFAULT now(),
    resolved boolean DEFAULT false,
    resolution text
);


--
-- Name: bug_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.bug_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bug_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.bug_events_id_seq OWNED BY maya_rp.bug_events.id;


--
-- Name: bug_tech_tree; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.bug_tech_tree (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    research_cost integer,
    prerequisite_id integer,
    unlocks character varying(100),
    unlock_type character varying(50)
);


--
-- Name: bug_tech_tree_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.bug_tech_tree_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bug_tech_tree_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.bug_tech_tree_id_seq OWNED BY maya_rp.bug_tech_tree.id;


--
-- Name: bug_war_assets; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.bug_war_assets (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    type character varying(50),
    description text,
    cost_credits integer,
    cost_resources jsonb,
    research_required character varying(100),
    effect jsonb,
    build_time_days integer
);


--
-- Name: bug_war_assets_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.bug_war_assets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bug_war_assets_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.bug_war_assets_id_seq OWNED BY maya_rp.bug_war_assets.id;


--
-- Name: build_queue; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.build_queue (
    id integer NOT NULL,
    session_id integer NOT NULL,
    project_name text NOT NULL,
    project_type text NOT NULL,
    status text DEFAULT 'queued'::text,
    alloy_cost bigint DEFAULT 0,
    fuel_cost bigint DEFAULT 0,
    credit_cost bigint DEFAULT 0,
    build_time_days integer DEFAULT 1,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    last_tick_at timestamp with time zone DEFAULT now()
);


--
-- Name: build_queue_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.build_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: build_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.build_queue_id_seq OWNED BY maya_rp.build_queue.id;


--
-- Name: build_templates; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.build_templates (
    id integer NOT NULL,
    name text NOT NULL,
    class_name text NOT NULL,
    tier integer DEFAULT 1 NOT NULL,
    ship_type text DEFAULT 'STD'::text NOT NULL,
    repeat_count integer DEFAULT 1 NOT NULL,
    priority integer DEFAULT 0
);


--
-- Name: build_templates_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.build_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: build_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.build_templates_id_seq OWNED BY maya_rp.build_templates.id;


--
-- Name: cabinet_decrees; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.cabinet_decrees (
    id integer NOT NULL,
    session_id integer NOT NULL,
    issued_by text NOT NULL,
    delegated_to integer,
    decree_type text NOT NULL,
    title text NOT NULL,
    description text,
    status text DEFAULT 'pending'::text NOT NULL,
    priority text DEFAULT 'standard'::text,
    secrecy_level text DEFAULT 'shadow'::text,
    impact_deltas jsonb DEFAULT '{}'::jsonb,
    cross_engine_hits jsonb DEFAULT '[]'::jsonb,
    issued_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT cabinet_decrees_decree_type_check CHECK ((decree_type = ANY (ARRAY['military'::text, 'diplomatic'::text, 'economic'::text, 'covert'::text, 'social'::text, 'education'::text, 'emergency'::text, 'directive'::text]))),
    CONSTRAINT cabinet_decrees_priority_check CHECK ((priority = ANY (ARRAY['low'::text, 'standard'::text, 'high'::text, 'critical'::text]))),
    CONSTRAINT cabinet_decrees_secrecy_level_check CHECK ((secrecy_level = ANY (ARRAY['public'::text, 'shadow'::text, 'classified'::text]))),
    CONSTRAINT cabinet_decrees_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'executing'::text, 'completed'::text, 'blocked'::text, 'overridden'::text])))
);


--
-- Name: cabinet_decrees_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.cabinet_decrees_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cabinet_decrees_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.cabinet_decrees_id_seq OWNED BY maya_rp.cabinet_decrees.id;


--
-- Name: cabinet_hierarchy; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.cabinet_hierarchy (
    id integer NOT NULL,
    session_id integer NOT NULL,
    tier integer DEFAULT 3 NOT NULL,
    title text NOT NULL,
    portfolio text,
    holder text NOT NULL,
    is_wife boolean DEFAULT false,
    wife_mode text DEFAULT 'laid_back'::text NOT NULL,
    can_deploy jsonb DEFAULT '[]'::jsonb,
    can_authorize jsonb DEFAULT '[]'::jsonb,
    max_fleet_power integer DEFAULT 0,
    reports_to integer,
    active boolean DEFAULT true,
    seated_at timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    leader_special boolean DEFAULT false,
    CONSTRAINT cabinet_hierarchy_tier_check CHECK (((tier >= 0) AND (tier <= 5))),
    CONSTRAINT cabinet_hierarchy_wife_mode_check CHECK ((wife_mode = ANY (ARRAY['laid_back'::text, 'advising'::text, 'executing'::text, 'emergency'::text])))
);


--
-- Name: cabinet_hierarchy_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.cabinet_hierarchy_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cabinet_hierarchy_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.cabinet_hierarchy_id_seq OWNED BY maya_rp.cabinet_hierarchy.id;


--
-- Name: cabinet_meetings; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.cabinet_meetings (
    id integer NOT NULL,
    session_id integer NOT NULL,
    meeting_type text NOT NULL,
    agenda text,
    attendees jsonb DEFAULT '[]'::jsonb,
    decisions jsonb DEFAULT '[]'::jsonb,
    cohesion integer,
    minutes text,
    convened_at timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT cabinet_meetings_meeting_type_check CHECK ((meeting_type = ANY (ARRAY['regular'::text, 'emergency'::text, 'war_council'::text, 'diplomatic'::text, 'covert'::text, 'ceremonial'::text])))
);


--
-- Name: cabinet_meetings_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.cabinet_meetings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cabinet_meetings_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.cabinet_meetings_id_seq OWNED BY maya_rp.cabinet_meetings.id;


--
-- Name: cargo; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.cargo (
    id integer NOT NULL,
    session_id integer,
    item_type text NOT NULL,
    quantity numeric NOT NULL,
    location_type text,
    location_id integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: cargo_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.cargo_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cargo_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.cargo_id_seq OWNED BY maya_rp.cargo.id;


--
-- Name: chapters; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.chapters (
    id integer NOT NULL,
    session_id integer NOT NULL,
    chapter_number integer NOT NULL,
    title text,
    exported boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: chapters_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.chapters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chapters_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.chapters_id_seq OWNED BY maya_rp.chapters.id;


--
-- Name: character_arcs; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_arcs (
    id integer NOT NULL,
    character_table character varying(50) NOT NULL,
    character_id integer NOT NULL,
    arc_name character varying(100),
    arc_description text,
    status character varying(20) DEFAULT 'inactive'::character varying,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    key_milestones jsonb
);


--
-- Name: character_arcs_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.character_arcs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: character_arcs_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.character_arcs_id_seq OWNED BY maya_rp.character_arcs.id;


--
-- Name: character_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_events (
    id integer NOT NULL,
    session_id integer,
    character_id integer,
    event_type character varying(50) NOT NULL,
    title character varying(200) NOT NULL,
    description text,
    tick_triggered integer,
    resolved boolean DEFAULT false,
    resolution text
);


--
-- Name: character_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.character_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: character_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.character_events_id_seq OWNED BY maya_rp.character_events.id;


--
-- Name: character_injuries; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_injuries (
    id integer NOT NULL,
    session_id integer,
    character_id integer,
    description text,
    severity character varying(20) DEFAULT 'moderate'::character varying,
    body_part character varying(50),
    cause character varying(50),
    received_game_day integer,
    heal_by_game_day integer,
    became_scar boolean DEFAULT false,
    status character varying(20) DEFAULT 'active'::character varying
);


--
-- Name: character_injuries_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.character_injuries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: character_injuries_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.character_injuries_id_seq OWNED BY maya_rp.character_injuries.id;


--
-- Name: character_memories; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_memories (
    id integer NOT NULL,
    session_id integer,
    character_id integer,
    memory_type text,
    content text NOT NULL,
    source_event_id integer,
    created_at_game_day integer,
    recalled_count integer DEFAULT 0,
    last_recalled_at_game_day integer,
    recall_trigger_keywords text[],
    emotional_weight integer DEFAULT 5,
    expires_at_game_day integer
);


--
-- Name: character_memories_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.character_memories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: character_memories_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.character_memories_id_seq OWNED BY maya_rp.character_memories.id;


--
-- Name: character_presence_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_presence_log (
    id integer NOT NULL,
    character_table character varying(50) NOT NULL,
    character_id integer NOT NULL,
    previous_presence character varying(20),
    new_presence character varying(20),
    changed_by character varying(50),
    changed_at timestamp without time zone DEFAULT now(),
    reason text
);


--
-- Name: character_presence_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.character_presence_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: character_presence_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.character_presence_log_id_seq OWNED BY maya_rp.character_presence_log.id;


--
-- Name: character_quirks; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_quirks (
    id integer NOT NULL,
    character_id integer,
    quirk_name character varying(100) NOT NULL,
    effect_type character varying(50),
    effect_value double precision DEFAULT 0,
    origin_story text,
    active boolean DEFAULT true
);


--
-- Name: character_quirks_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.character_quirks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: character_quirks_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.character_quirks_id_seq OWNED BY maya_rp.character_quirks.id;


--
-- Name: character_relationships; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_relationships (
    id integer NOT NULL,
    session_id integer,
    char_a_id integer,
    char_b_id integer,
    score integer DEFAULT 0,
    relationship_type character varying(50),
    last_interaction timestamp with time zone
);


--
-- Name: character_relationships_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.character_relationships_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: character_relationships_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.character_relationships_id_seq OWNED BY maya_rp.character_relationships.id;


--
-- Name: character_species; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_species (
    character_id integer NOT NULL,
    species_id integer NOT NULL,
    purity_pct integer DEFAULT 100
);


--
-- Name: character_traits; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.character_traits (
    id integer NOT NULL,
    character_id integer,
    trait text NOT NULL,
    trait_type text DEFAULT 'innate'::text,
    source text DEFAULT ''::text,
    value numeric DEFAULT 0,
    active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: character_traits_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.character_traits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: character_traits_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.character_traits_id_seq OWNED BY maya_rp.character_traits.id;


--
-- Name: characters; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.characters (
    id integer NOT NULL,
    session_id integer DEFAULT 1 NOT NULL,
    name text NOT NULL,
    role text,
    archetype text,
    bond integer DEFAULT 0,
    status text DEFAULT 'active'::text NOT NULL,
    traits jsonb DEFAULT '[]'::jsonb,
    romance_flag boolean DEFAULT false,
    romance_stage text DEFAULT 'strangers'::text,
    last_romance_scene text,
    morality integer DEFAULT 0,
    is_spouse boolean DEFAULT false,
    character_type character varying(20) DEFAULT 'supporting'::character varying,
    controlled_by character varying(10) DEFAULT 'ai'::character varying,
    presence character varying(20) DEFAULT 'available'::character varying,
    scene_location character varying(100),
    relationship_to_player integer DEFAULT 0,
    importance integer DEFAULT 1,
    voice_profile text,
    dialogue_style text,
    profile_jsonb jsonb DEFAULT '{}'::jsonb,
    wardrobe_jsonb jsonb DEFAULT '[]'::jsonb,
    current_outfit jsonb DEFAULT '{}'::jsonb,
    inventory_jsonb jsonb DEFAULT '[]'::jsonb,
    species text,
    species_id integer,
    faction_id integer,
    crew_id integer,
    ship_id integer,
    clearance_level integer DEFAULT 1,
    screened boolean DEFAULT false,
    beauty_catalog_id integer,
    origin_system text,
    bond_level integer DEFAULT 0,
    dream_essence_affinity numeric DEFAULT 0,
    last_seen_day integer,
    background text,
    appearance text,
    description text,
    beauty_standard boolean DEFAULT false,
    modified boolean DEFAULT false,
    scene_territory_id integer,
    mother_id integer,
    father_id integer,
    house_name text,
    birth_house text,
    family_system text DEFAULT 'old_way'::text,
    succession text DEFAULT 'patrilineal'::text,
    CONSTRAINT characters_family_system_check CHECK ((family_system = ANY (ARRAY['old_way'::text, 'setia_new_way'::text]))),
    CONSTRAINT characters_morality_check CHECK (((morality >= '-100'::integer) AND (morality <= 100))),
    CONSTRAINT characters_succession_check CHECK ((succession = ANY (ARRAY['patrilineal'::text, 'matrilineal'::text, 'all_heirs'::text, 'elective'::text, 'titled_only'::text])))
);


--
-- Name: characters_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.characters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: characters_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.characters_id_seq OWNED BY maya_rp.characters.id;


--
-- Name: leaders; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.leaders (
    id integer NOT NULL,
    faction_id integer,
    name character varying(100) NOT NULL,
    age integer DEFAULT 30,
    gender character varying(10),
    traits jsonb,
    stats jsonb,
    approval integer DEFAULT 50,
    heir_id integer,
    active boolean DEFAULT true,
    assumed_power_at timestamp without time zone DEFAULT now(),
    last_activity timestamp without time zone,
    character_type character varying(20) DEFAULT 'main'::character varying,
    controlled_by character varying(10) DEFAULT 'ai'::character varying,
    presence character varying(20) DEFAULT 'available'::character varying,
    scene_location character varying(100)
);


--
-- Name: characters_unified; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.characters_unified AS
 SELECT 'characters'::text AS source,
    characters.id,
    characters.name,
    characters.character_type,
    characters.controlled_by,
    characters.presence,
    characters.scene_location,
    characters.importance,
    characters.relationship_to_player
   FROM maya_rp.characters
UNION ALL
 SELECT 'leaders'::text AS source,
    leaders.id,
    leaders.name,
    leaders.character_type,
    leaders.controlled_by,
    leaders.presence,
    leaders.scene_location,
    5 AS importance,
    0 AS relationship_to_player
   FROM maya_rp.leaders;


--
-- Name: chekhov_elements; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.chekhov_elements (
    id integer NOT NULL,
    session_id integer,
    element_type character varying(30),
    description text,
    importance character varying(20) DEFAULT 'medium'::character varying,
    introduced_game_day integer,
    payoff_deadline integer,
    payoff_method text,
    paid_game_day integer,
    status character varying(20) DEFAULT 'unpaid'::character varying
);


--
-- Name: chekhov_elements_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.chekhov_elements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chekhov_elements_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.chekhov_elements_id_seq OWNED BY maya_rp.chekhov_elements.id;


--
-- Name: choices; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.choices (
    id integer NOT NULL,
    session_id integer NOT NULL,
    turn_no integer,
    situation text,
    options jsonb,
    picked text,
    consequence text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: choices_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.choices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: choices_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.choices_id_seq OWNED BY maya_rp.choices.id;


--
-- Name: clues; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.clues (
    id integer NOT NULL,
    session_id integer NOT NULL,
    source text NOT NULL,
    source_type text DEFAULT 'discovery'::text NOT NULL,
    text text NOT NULL,
    connects_to_clue integer,
    revealed boolean DEFAULT false,
    revealed_by_character integer,
    location_id integer,
    session_found integer,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT clues_source_type_check CHECK ((source_type = ANY (ARRAY['discovery'::text, 'interrogation'::text, 'companion_insight'::text, 'scan'::text, 'artifact'::text, 'document'::text, 'testimony'::text])))
);


--
-- Name: clues_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.clues_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: clues_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.clues_id_seq OWNED BY maya_rp.clues.id;


--
-- Name: colonies; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.colonies (
    id integer NOT NULL,
    session_id integer DEFAULT 1 NOT NULL,
    name text NOT NULL,
    planet_type text,
    population bigint DEFAULT 0,
    development integer DEFAULT 0,
    alloy_output integer DEFAULT 0,
    fuel_output integer DEFAULT 0,
    credit_output integer DEFAULT 0,
    status text DEFAULT 'developing'::text NOT NULL
);


--
-- Name: colonies_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.colonies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: colonies_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.colonies_id_seq OWNED BY maya_rp.colonies.id;


--
-- Name: colonization_projects; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.colonization_projects (
    id integer NOT NULL,
    planet_id integer,
    colony_name character varying(100),
    ship_id integer,
    started_at timestamp without time zone DEFAULT now(),
    progress_pct integer DEFAULT 0,
    required_credits integer DEFAULT 100000,
    required_resources jsonb,
    status character varying(20) DEFAULT 'planned'::character varying,
    completed_at timestamp without time zone
);


--
-- Name: colonization_projects_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.colonization_projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: colonization_projects_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.colonization_projects_id_seq OWNED BY maya_rp.colonization_projects.id;


--
-- Name: combat_results; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.combat_results (
    id integer NOT NULL,
    tactical_state_id integer NOT NULL,
    session_id integer NOT NULL,
    difficulty text,
    encounter_size text,
    player_power integer,
    enemy_power integer,
    ships_lost jsonb DEFAULT '[]'::jsonb,
    ships_damaged jsonb DEFAULT '[]'::jsonb,
    ships_captured jsonb DEFAULT '[]'::jsonb,
    crew_casualties integer DEFAULT 0,
    survivors_captured integer DEFAULT 0,
    enemy_ships_destroyed integer DEFAULT 0,
    enemy_ships_routed integer DEFAULT 0,
    territory_change jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    retreat_attempted boolean DEFAULT false,
    retreat_successful boolean DEFAULT false,
    pursuit_damage integer DEFAULT 0,
    CONSTRAINT combat_results_difficulty_check CHECK ((difficulty = ANY (ARRAY['trivial'::text, 'easy'::text, 'fair'::text, 'hard'::text, 'deadly'::text, 'impossible'::text]))),
    CONSTRAINT combat_results_encounter_size_check CHECK ((encounter_size = ANY (ARRAY['skirmish'::text, 'engagement'::text, 'battle'::text, 'fleet_action'::text, 'armada'::text])))
);


--
-- Name: combat_results_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.combat_results_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: combat_results_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.combat_results_id_seq OWNED BY maya_rp.combat_results.id;


--
-- Name: combat_rounds; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.combat_rounds (
    id integer NOT NULL,
    tactical_state_id integer NOT NULL,
    round_number integer NOT NULL,
    system_state jsonb,
    ai_prose text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: combat_rounds_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.combat_rounds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: combat_rounds_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.combat_rounds_id_seq OWNED BY maya_rp.combat_rounds.id;


--
-- Name: combat_stats; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.combat_stats (
    id integer NOT NULL,
    ship_id integer NOT NULL,
    hull_points integer DEFAULT 500 NOT NULL,
    max_hull_points integer DEFAULT 500 NOT NULL,
    shield_points integer DEFAULT 300 NOT NULL,
    max_shield_points integer DEFAULT 300 NOT NULL,
    weapon_systems jsonb DEFAULT '[]'::jsonb,
    speed text DEFAULT 'medium'::text NOT NULL,
    evasion integer DEFAULT 30 NOT NULL,
    combat_rating integer DEFAULT 50 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT combat_stats_evasion_check CHECK (((evasion >= 0) AND (evasion <= 100))),
    CONSTRAINT combat_stats_speed_check CHECK ((speed = ANY (ARRAY['very_slow'::text, 'slow'::text, 'medium'::text, 'fast'::text, 'very_fast'::text])))
);


--
-- Name: combat_stats_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.combat_stats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: combat_stats_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.combat_stats_id_seq OWNED BY maya_rp.combat_stats.id;


--
-- Name: commodities; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.commodities (
    id integer NOT NULL,
    session_id integer,
    name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    base_price double precision DEFAULT 10.0 NOT NULL,
    current_price double precision DEFAULT 10.0 NOT NULL,
    volatility double precision DEFAULT 0.05,
    supply double precision DEFAULT 1000,
    demand double precision DEFAULT 1000,
    last_tick_at integer DEFAULT 0
);


--
-- Name: commodities_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.commodities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: commodities_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.commodities_id_seq OWNED BY maya_rp.commodities.id;


--
-- Name: complaint_boxes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.complaint_boxes (
    id integer NOT NULL,
    session_id integer NOT NULL,
    planet_id integer,
    territory_id integer,
    location text,
    status text DEFAULT 'active'::text,
    beat_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: complaint_boxes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.complaint_boxes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: complaint_boxes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.complaint_boxes_id_seq OWNED BY maya_rp.complaint_boxes.id;


--
-- Name: complaints; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.complaints (
    id integer NOT NULL,
    session_id integer NOT NULL,
    box_id integer,
    planet_id integer,
    territory_id integer,
    complaint text NOT NULL,
    category text,
    mood text,
    anonymous boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: complaints_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.complaints_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: complaints_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.complaints_id_seq OWNED BY maya_rp.complaints.id;


--
-- Name: consequence_seeds; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.consequence_seeds (
    id integer NOT NULL,
    session_id integer,
    trigger_type text,
    cause_description text,
    effects_jsonb jsonb DEFAULT '[]'::jsonb,
    planted_at_tick integer,
    can_be_prevented boolean DEFAULT false,
    prevention_action text,
    prevention_method text,
    status text DEFAULT 'planted'::text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: consequence_seeds_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.consequence_seeds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: consequence_seeds_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.consequence_seeds_id_seq OWNED BY maya_rp.consequence_seeds.id;


--
-- Name: containment_measures; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.containment_measures (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    category character varying(50),
    effectiveness numeric DEFAULT 1.0,
    cost_credits integer,
    cost_resources jsonb,
    research_required character varying(100),
    build_time_days integer
);


--
-- Name: containment_measures_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.containment_measures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: containment_measures_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.containment_measures_id_seq OWNED BY maya_rp.containment_measures.id;


--
-- Name: conversation_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.conversation_log (
    id integer NOT NULL,
    session_id integer,
    character_id integer,
    topic text,
    keywords text[],
    outcome text,
    emotional_beat character varying(20) DEFAULT 'neutral'::character varying,
    game_day integer
);


--
-- Name: conversation_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.conversation_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversation_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.conversation_log_id_seq OWNED BY maya_rp.conversation_log.id;


--
-- Name: corporate_assets; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.corporate_assets (
    id integer NOT NULL,
    corporation_id integer,
    asset_type character varying(50),
    location_id integer,
    value integer,
    income_per_day integer DEFAULT 1000,
    status character varying(20) DEFAULT 'active'::character varying
);


--
-- Name: corporate_assets_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.corporate_assets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: corporate_assets_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.corporate_assets_id_seq OWNED BY maya_rp.corporate_assets.id;


--
-- Name: corporate_contracts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.corporate_contracts (
    id integer NOT NULL,
    session_id integer NOT NULL,
    corp_id integer,
    contract_type text NOT NULL,
    target_system text,
    payout_credits bigint DEFAULT 0,
    payout_alloys bigint DEFAULT 0,
    duration_days integer NOT NULL,
    days_remaining integer NOT NULL,
    status text DEFAULT 'active'::text,
    target_territory_id integer
);


--
-- Name: corporate_contracts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.corporate_contracts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: corporate_contracts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.corporate_contracts_id_seq OWNED BY maya_rp.corporate_contracts.id;


--
-- Name: corporations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.corporations (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    faction_id integer,
    industry character varying(50),
    treasury bigint DEFAULT 1000000,
    influence integer DEFAULT 10,
    profit_margin numeric DEFAULT 0.1,
    created_at timestamp without time zone DEFAULT now(),
    session_id integer NOT NULL,
    ceo_character_id integer,
    tier integer DEFAULT 1,
    efficiency integer DEFAULT 50,
    standing integer DEFAULT 50,
    status text DEFAULT 'active'::text,
    created_at_game_day integer
);


--
-- Name: corporations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.corporations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: corporations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.corporations_id_seq OWNED BY maya_rp.corporations.id;


--
-- Name: counter_intel_ops; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.counter_intel_ops (
    id integer NOT NULL,
    faction_id integer,
    against_faction_id integer,
    operation_type character varying(50) DEFAULT 'detect'::character varying,
    started_at timestamp without time zone DEFAULT now(),
    completed_at timestamp without time zone,
    success boolean,
    details jsonb
);


--
-- Name: counter_intel_ops_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.counter_intel_ops_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: counter_intel_ops_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.counter_intel_ops_id_seq OWNED BY maya_rp.counter_intel_ops.id;


--
-- Name: crew_allocation_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.crew_allocation_log (
    id integer NOT NULL,
    session_id integer,
    game_day integer,
    ship_id integer,
    ship_name text,
    crew_assigned integer,
    source text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: crew_allocation_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.crew_allocation_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crew_allocation_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.crew_allocation_log_id_seq OWNED BY maya_rp.crew_allocation_log.id;


--
-- Name: crew_consumption_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.crew_consumption_log (
    id integer NOT NULL,
    session_id integer,
    game_day integer,
    ship_id integer,
    ship_name text,
    amount integer,
    pool_after bigint,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: crew_consumption_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.crew_consumption_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crew_consumption_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.crew_consumption_log_id_seq OWNED BY maya_rp.crew_consumption_log.id;


--
-- Name: crew_factions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.crew_factions (
    id integer NOT NULL,
    ship_id integer NOT NULL,
    name text NOT NULL,
    leader_crew_id integer,
    alignment text DEFAULT 'neutral'::text,
    member_count integer DEFAULT 0,
    agenda text,
    morale integer DEFAULT 50,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: crew_factions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.crew_factions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crew_factions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.crew_factions_id_seq OWNED BY maya_rp.crew_factions.id;


--
-- Name: crew_production_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.crew_production_log (
    id integer NOT NULL,
    session_id integer,
    game_day integer,
    source text,
    amount integer,
    pool_after bigint,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: crew_production_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.crew_production_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crew_production_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.crew_production_log_id_seq OWNED BY maya_rp.crew_production_log.id;


--
-- Name: crew_roster; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.crew_roster (
    id integer NOT NULL,
    session_id integer DEFAULT 1 NOT NULL,
    ship_id integer,
    name text NOT NULL,
    role text,
    bond integer DEFAULT 0,
    status text DEFAULT 'active'::text NOT NULL,
    morale integer DEFAULT 50,
    loyalty_flag text DEFAULT 'neutral'::text,
    faction_alignment text,
    personality_traits jsonb DEFAULT '[]'::jsonb,
    talent_points integer DEFAULT 0,
    talent_tree jsonb DEFAULT '[]'::jsonb,
    level integer DEFAULT 1,
    xp integer DEFAULT 0,
    sanity integer DEFAULT 100,
    traumas jsonb DEFAULT '[]'::jsonb,
    personality_notes text,
    specialization text,
    promotion_source text,
    clearance_level integer DEFAULT 1,
    screened boolean DEFAULT false,
    CONSTRAINT crew_roster_loyalty_flag_check CHECK (((loyalty_flag IS NULL) OR (loyalty_flag = ANY (ARRAY['loyal'::text, 'neutral'::text, 'disloyal'::text, 'wavering'::text])))),
    CONSTRAINT crew_roster_sanity_check CHECK (((sanity >= 0) AND (sanity <= 100)))
);


--
-- Name: crew_roster_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.crew_roster_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crew_roster_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.crew_roster_id_seq OWNED BY maya_rp.crew_roster.id;


--
-- Name: crew_skills; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.crew_skills (
    id integer NOT NULL,
    crew_id integer,
    session_id integer,
    skill_name text,
    proficiency integer DEFAULT 1
);


--
-- Name: crew_skills_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.crew_skills_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crew_skills_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.crew_skills_id_seq OWNED BY maya_rp.crew_skills.id;


--
-- Name: crew_xp_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.crew_xp_log (
    id integer NOT NULL,
    crew_id integer,
    session_id integer,
    amount integer,
    source text,
    recorded_at timestamp with time zone DEFAULT now()
);


--
-- Name: crew_xp_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.crew_xp_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crew_xp_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.crew_xp_log_id_seq OWNED BY maya_rp.crew_xp_log.id;


--
-- Name: crisis_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.crisis_events (
    id integer NOT NULL,
    session_id integer,
    crisis_type character varying(50) NOT NULL,
    severity integer DEFAULT 1,
    started_at timestamp without time zone DEFAULT now(),
    resolved_at timestamp without time zone,
    description text
);


--
-- Name: crisis_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.crisis_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crisis_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.crisis_events_id_seq OWNED BY maya_rp.crisis_events.id;


--
-- Name: damage_resistances; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.damage_resistances (
    id integer NOT NULL,
    entity_type character varying(50),
    entity_id integer,
    resistance_type character varying(50),
    value double precision
);


--
-- Name: damage_resistances_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.damage_resistances_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: damage_resistances_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.damage_resistances_id_seq OWNED BY maya_rp.damage_resistances.id;


--
-- Name: dark_ops; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.dark_ops (
    id integer NOT NULL,
    session_id integer NOT NULL,
    target_type text NOT NULL,
    target_name text NOT NULL,
    operation text NOT NULL,
    success_chance integer DEFAULT 50,
    collateral integer DEFAULT 0,
    reputation_delta integer DEFAULT '-20'::integer,
    outcome text,
    narrative text,
    launched_at timestamp with time zone DEFAULT now(),
    resolved_at timestamp with time zone,
    CONSTRAINT dark_ops_operation_check CHECK ((operation = ANY (ARRAY['assassinate'::text, 'sabotage'::text, 'terror'::text, 'planet_crack'::text, 'enslave'::text, 'purge'::text, 'interrogate_hard'::text]))),
    CONSTRAINT dark_ops_outcome_check CHECK ((outcome = ANY (ARRAY['pending'::text, 'success'::text, 'failure'::text, 'exposed'::text]))),
    CONSTRAINT dark_ops_target_type_check CHECK ((target_type = ANY (ARRAY['faction'::text, 'planet'::text, 'character'::text, 'colony'::text])))
);


--
-- Name: dark_ops_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.dark_ops_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dark_ops_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.dark_ops_id_seq OWNED BY maya_rp.dark_ops.id;


--
-- Name: defense_installations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.defense_installations (
    id integer NOT NULL,
    session_id integer,
    colony_id integer,
    system_name text,
    installation_type text,
    level integer DEFAULT 1,
    defense_rating integer DEFAULT 100,
    upkeep_credits integer DEFAULT 20,
    status text DEFAULT 'active'::text,
    territory_id integer
);


--
-- Name: defense_installations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.defense_installations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: defense_installations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.defense_installations_id_seq OWNED BY maya_rp.defense_installations.id;


--
-- Name: difficulty_tiers; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.difficulty_tiers (
    id integer NOT NULL,
    tier_name text NOT NULL,
    dc integer NOT NULL,
    color text,
    description text
);


--
-- Name: difficulty_tiers_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.difficulty_tiers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: difficulty_tiers_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.difficulty_tiers_id_seq OWNED BY maya_rp.difficulty_tiers.id;


--
-- Name: dig_sites; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.dig_sites (
    id integer NOT NULL,
    session_id integer,
    sector_id integer,
    name character varying(200) NOT NULL,
    site_type character varying(50) NOT NULL,
    difficulty integer DEFAULT 1,
    excavation_progress integer DEFAULT 0,
    max_progress integer DEFAULT 100,
    status character varying(20) DEFAULT 'undiscovered'::character varying,
    artifact_yield integer DEFAULT 1,
    requires_special_equip character varying(100),
    discovered_at timestamp with time zone
);


--
-- Name: dig_sites_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.dig_sites_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dig_sites_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.dig_sites_id_seq OWNED BY maya_rp.dig_sites.id;


--
-- Name: diplomatic_actions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.diplomatic_actions (
    id integer NOT NULL,
    action_type character varying(50) NOT NULL,
    actor_faction_id integer,
    target_faction_id integer,
    treaty_id integer,
    details jsonb,
    happened_at timestamp without time zone DEFAULT now(),
    success boolean,
    response text
);


--
-- Name: diplomatic_actions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.diplomatic_actions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diplomatic_actions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.diplomatic_actions_id_seq OWNED BY maya_rp.diplomatic_actions.id;


--
-- Name: factions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.factions (
    id integer NOT NULL,
    session_id integer DEFAULT 1 NOT NULL,
    name text NOT NULL,
    standing text DEFAULT 'neutral'::text,
    trust text DEFAULT 'low'::text,
    fear_of_player integer DEFAULT 0,
    treasury bigint DEFAULT 1000000,
    economic_strength numeric DEFAULT 1.0,
    trade_aggressiveness numeric DEFAULT 0.5,
    last_economic_tick timestamp without time zone,
    reputation integer DEFAULT 0,
    diplomatic_power integer DEFAULT 50,
    last_diplomatic_tick timestamp without time zone,
    ai_personality jsonb,
    ai_goals jsonb,
    is_pirate boolean DEFAULT false,
    pirate_aggressiveness numeric DEFAULT 0.5,
    pirate_base_system_id integer,
    pirate_fleet_power integer DEFAULT 100,
    pirate_reputation integer DEFAULT 0,
    slave_trade_reputation integer DEFAULT 0,
    status text DEFAULT 'active'::text
);


--
-- Name: treaties; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.treaties (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    treaty_type character varying(50) NOT NULL,
    faction_a_id integer,
    faction_b_id integer,
    signed_at timestamp without time zone DEFAULT now(),
    duration_days integer DEFAULT 365,
    expires_at timestamp without time zone,
    active boolean DEFAULT true,
    terms jsonb,
    created_by character varying(50)
);


--
-- Name: diplomatic_overview; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.diplomatic_overview AS
 SELECT id,
    name,
    standing,
    reputation,
    diplomatic_power,
    ( SELECT json_agg(json_build_object('type', t.treaty_type, 'with', f2.name, 'active', t.active)) AS json_agg
           FROM (maya_rp.treaties t
             LEFT JOIN maya_rp.factions f2 ON ((f2.id =
                CASE
                    WHEN (t.faction_a_id = f.id) THEN t.faction_b_id
                    ELSE t.faction_a_id
                END)))
          WHERE (((t.faction_a_id = f.id) OR (t.faction_b_id = f.id)) AND (t.active = true))) AS active_treaties
   FROM maya_rp.factions f
  WHERE (session_id = 3);


--
-- Name: disaster_templates; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.disaster_templates (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    severity_min integer DEFAULT 1,
    severity_max integer DEFAULT 5,
    base_damage double precision DEFAULT 10.0,
    duration_ticks integer DEFAULT 3,
    trigger_weight double precision DEFAULT 1.0,
    description text
);


--
-- Name: disaster_templates_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.disaster_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: disaster_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.disaster_templates_id_seq OWNED BY maya_rp.disaster_templates.id;


--
-- Name: discoveries; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.discoveries (
    id integer NOT NULL,
    session_id integer,
    type character varying(30) NOT NULL,
    target_id integer NOT NULL,
    discovered_at timestamp without time zone DEFAULT now(),
    explored boolean DEFAULT false,
    explored_at timestamp without time zone,
    results jsonb
);


--
-- Name: discoveries_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.discoveries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: discoveries_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.discoveries_id_seq OWNED BY maya_rp.discoveries.id;


--
-- Name: duels; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.duels (
    id integer NOT NULL,
    session_id integer,
    player_ship_id integer,
    opponent_name text,
    opponent_tier integer,
    opponent_hull integer,
    opponent_power integer,
    stakes_type text,
    stakes_value text,
    venue text,
    status text DEFAULT 'pending'::text,
    result text,
    created_at timestamp with time zone DEFAULT now(),
    resolved_at timestamp with time zone
);


--
-- Name: duels_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.duels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: duels_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.duels_id_seq OWNED BY maya_rp.duels.id;


--
-- Name: economic_crises; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.economic_crises (
    id integer NOT NULL,
    territory_id integer,
    crisis_type character varying(50) NOT NULL,
    severity integer,
    triggered_by character varying(100),
    started_at timestamp without time zone DEFAULT now(),
    resolved_at timestamp without time zone,
    resolution character varying(255),
    event_type character varying(50) DEFAULT 'rebellion'::character varying,
    scope character varying(50) DEFAULT 'territory'::character varying,
    progress integer DEFAULT 0,
    CONSTRAINT economic_crises_severity_check CHECK (((severity >= 1) AND (severity <= 10)))
);


--
-- Name: economic_crises_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.economic_crises_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: economic_crises_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.economic_crises_id_seq OWNED BY maya_rp.economic_crises.id;


--
-- Name: territory; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.territory (
    id integer NOT NULL,
    session_id integer NOT NULL,
    system_name text NOT NULL,
    location_id integer,
    controlling_faction text NOT NULL,
    contested_by text,
    fleet_presence integer DEFAULT 0,
    defensive_rating integer DEFAULT 0,
    last_battle_session integer,
    last_campaign integer,
    status text DEFAULT 'controlled'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    population bigint DEFAULT 1000000,
    tax_rate numeric DEFAULT 0.05,
    development_level integer DEFAULT 1,
    birth_rate numeric DEFAULT 0.025,
    max_population bigint DEFAULT 10000000,
    economic_output numeric DEFAULT 1.0,
    last_population_update timestamp without time zone,
    crisis_level integer DEFAULT 0,
    crisis_type character varying(50),
    governor_name character varying(100),
    trade_income numeric DEFAULT 0,
    military_consumption numeric DEFAULT 0,
    research_points integer DEFAULT 0,
    slave_population integer DEFAULT 0,
    slave_productivity_mult numeric DEFAULT 1.0,
    slave_revolt_risk integer DEFAULT 0,
    morale integer DEFAULT 50,
    revocation_risk integer DEFAULT 0,
    title_performance integer DEFAULT 0,
    requires_king_prompt boolean DEFAULT false,
    CONSTRAINT territory_status_check CHECK ((status = ANY (ARRAY['controlled'::text, 'contested'::text, 'besieged'::text, 'lost'::text, 'abandoned'::text, 'neutral'::text])))
);


--
-- Name: economic_dashboard; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.economic_dashboard AS
 SELECT id,
    system_name,
    controlling_faction,
    population,
    tax_rate,
    development_level,
    crisis_level,
    ((((population)::numeric * tax_rate) * ((1)::numeric + (((development_level - 1))::numeric * 0.1))))::bigint AS daily_tax_revenue,
    trade_income,
    military_consumption,
    research_points
   FROM maya_rp.territory t
  WHERE (session_id = 3);


--
-- Name: economic_overview; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.economic_overview AS
 SELECT id,
    system_name,
    controlling_faction,
    population,
    tax_rate,
    development_level,
    crisis_level,
    crisis_type,
    governor_name,
        CASE
            WHEN (status = 'controlled'::text) THEN ((((population)::numeric * tax_rate) * ((1)::numeric + (((development_level - 1))::numeric * 0.1))))::bigint
            ELSE (0)::bigint
        END AS estimated_daily_revenue
   FROM maya_rp.territory t
  WHERE ((session_id = 3) AND (controlling_faction = 'TKG Provisional Council'::text))
  ORDER BY system_name;


--
-- Name: economic_tracker; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.economic_tracker (
    id integer NOT NULL,
    session_id integer,
    tick_date timestamp with time zone DEFAULT now(),
    income_alloys bigint DEFAULT 0,
    income_fuel bigint DEFAULT 0,
    income_credits bigint DEFAULT 0,
    expense_alloys bigint DEFAULT 0,
    expense_fuel bigint DEFAULT 0,
    expense_credits bigint DEFAULT 0,
    balance_alloys bigint DEFAULT 25000000,
    balance_fuel bigint DEFAULT 25000000,
    balance_credits bigint DEFAULT 25000000,
    notes text DEFAULT ''::text
);


--
-- Name: economic_tracker_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.economic_tracker_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: economic_tracker_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.economic_tracker_id_seq OWNED BY maya_rp.economic_tracker.id;


--
-- Name: enrolled_crew; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.enrolled_crew (
    id integer NOT NULL,
    crew_id integer,
    program_id integer,
    campus_id integer,
    progress integer DEFAULT 0,
    target_progress integer DEFAULT 100,
    graduated boolean DEFAULT false
);


--
-- Name: enrolled_crew_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.enrolled_crew_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enrolled_crew_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.enrolled_crew_id_seq OWNED BY maya_rp.enrolled_crew.id;


--
-- Name: envoys; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.envoys (
    id integer NOT NULL,
    faction_id integer,
    target_faction_id integer,
    envoy_name character varying(100),
    mission_type character varying(50),
    started_at timestamp without time zone DEFAULT now(),
    duration_days integer DEFAULT 30,
    status character varying(20) DEFAULT 'active'::character varying,
    result jsonb
);


--
-- Name: envoys_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.envoys_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: envoys_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.envoys_id_seq OWNED BY maya_rp.envoys.id;


--
-- Name: eradication_campaigns; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.eradication_campaigns (
    id integer NOT NULL,
    session_id integer,
    target_infestation_id integer,
    campaign_name character varying(100),
    started_at timestamp without time zone DEFAULT now(),
    completed_at timestamp without time zone,
    progress integer DEFAULT 0,
    strategy character varying(50),
    assets_assigned jsonb,
    status character varying(20) DEFAULT 'active'::character varying,
    casualties integer DEFAULT 0,
    resources_consumed jsonb
);


--
-- Name: eradication_campaigns_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.eradication_campaigns_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: eradication_campaigns_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.eradication_campaigns_id_seq OWNED BY maya_rp.eradication_campaigns.id;


--
-- Name: escape_countermeasures; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.escape_countermeasures (
    id integer NOT NULL,
    session_id integer NOT NULL,
    prisoner_id integer,
    measure_type text NOT NULL,
    cost_credits integer,
    risk_reduction numeric,
    applied_at timestamp with time zone DEFAULT now()
);


--
-- Name: escape_countermeasures_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.escape_countermeasures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: escape_countermeasures_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.escape_countermeasures_id_seq OWNED BY maya_rp.escape_countermeasures.id;


--
-- Name: espionage_missions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.espionage_missions (
    id integer NOT NULL,
    session_id integer NOT NULL,
    faction_id integer NOT NULL,
    mission_type text NOT NULL,
    agent_name text NOT NULL,
    difficulty integer DEFAULT 50,
    success_chance integer DEFAULT 50,
    outcome text,
    loot_json jsonb DEFAULT '{}'::jsonb,
    reputation_delta integer DEFAULT 0,
    narrative text,
    launched_at timestamp with time zone DEFAULT now(),
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT espionage_missions_difficulty_check CHECK (((difficulty >= 1) AND (difficulty <= 100))),
    CONSTRAINT espionage_missions_mission_type_check CHECK ((mission_type = ANY (ARRAY['sabotage'::text, 'steal_tech'::text, 'assassinate'::text, 'plant_rumor'::text, 'scout_fleet'::text, 'steal_resources'::text]))),
    CONSTRAINT espionage_missions_outcome_check CHECK ((outcome = ANY (ARRAY['pending'::text, 'success'::text, 'failure'::text, 'critical_failure'::text, 'detected'::text, 'captured'::text])))
);


--
-- Name: espionage_missions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.espionage_missions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: espionage_missions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.espionage_missions_id_seq OWNED BY maya_rp.espionage_missions.id;


--
-- Name: espionage_operations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.espionage_operations (
    id integer NOT NULL,
    spy_network_id integer,
    operation_type character varying(50) NOT NULL,
    target_details jsonb,
    success boolean DEFAULT false,
    started_at timestamp without time zone DEFAULT now(),
    completed_at timestamp without time zone,
    result jsonb,
    cost_credits integer DEFAULT 0,
    risk integer DEFAULT 50
);


--
-- Name: espionage_operations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.espionage_operations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: espionage_operations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.espionage_operations_id_seq OWNED BY maya_rp.espionage_operations.id;


--
-- Name: event_templates; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.event_templates (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    category character varying(50),
    trigger_conditions jsonb,
    effects jsonb,
    min_occurrence_days integer DEFAULT 30,
    max_occurrence_days integer DEFAULT 365,
    probability numeric DEFAULT 0.01
);


--
-- Name: event_templates_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.event_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: event_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.event_templates_id_seq OWNED BY maya_rp.event_templates.id;


--
-- Name: events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.events (
    id bigint NOT NULL,
    session_id integer DEFAULT 1 NOT NULL,
    happened_at timestamp with time zone DEFAULT now(),
    event_type text NOT NULL,
    title text NOT NULL,
    description text,
    tags jsonb DEFAULT '[]'::jsonb,
    narrative_content text,
    narrative_title character varying(200),
    importance integer DEFAULT 1,
    embedding public.vector(768)
);


--
-- Name: events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.events_id_seq OWNED BY maya_rp.events.id;


--
-- Name: faction_ai_state; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.faction_ai_state (
    id integer NOT NULL,
    session_id integer,
    faction_name character varying(100) NOT NULL,
    aggression integer DEFAULT 50,
    expansionism integer DEFAULT 50,
    xenophobia integer DEFAULT 50,
    militarism integer DEFAULT 50,
    economic_focus integer DEFAULT 50,
    last_decision_tick integer DEFAULT 0,
    decision_cooldown integer DEFAULT 5
);


--
-- Name: faction_ai_state_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.faction_ai_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faction_ai_state_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.faction_ai_state_id_seq OWNED BY maya_rp.faction_ai_state.id;


--
-- Name: faction_policies; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.faction_policies (
    id integer NOT NULL,
    session_id integer,
    faction_id integer,
    category text,
    policy_key text,
    selected_option text,
    modified_by text,
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: faction_policies_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.faction_policies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faction_policies_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.faction_policies_id_seq OWNED BY maya_rp.faction_policies.id;


--
-- Name: faction_relations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.faction_relations (
    id integer NOT NULL,
    session_id integer,
    faction_a integer,
    faction_b integer,
    standing text DEFAULT 'neutral'::text,
    trade_volume numeric DEFAULT 0,
    military_tension numeric DEFAULT 0,
    last_interaction text,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: faction_relations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.faction_relations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faction_relations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.faction_relations_id_seq OWNED BY maya_rp.faction_relations.id;


--
-- Name: faction_ships; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.faction_ships (
    id integer NOT NULL,
    session_id integer NOT NULL,
    faction_name text NOT NULL,
    ship_name text NOT NULL,
    class_name text NOT NULL,
    ship_type text DEFAULT 'STD'::text NOT NULL,
    tier integer DEFAULT 1 NOT NULL,
    mass integer DEFAULT 0 NOT NULL,
    hull integer DEFAULT 0 NOT NULL,
    speed integer DEFAULT 0 NOT NULL,
    crew integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    power_rating integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    destroyed_at timestamp with time zone,
    CONSTRAINT faction_ships_status_check CHECK ((status = ANY (ARRAY['active'::text, 'damaged'::text, 'derelict'::text, 'destroyed'::text, 'scuttled'::text])))
);


--
-- Name: faction_ships_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.faction_ships_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faction_ships_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.faction_ships_id_seq OWNED BY maya_rp.faction_ships.id;


--
-- Name: faction_slave_policy; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.faction_slave_policy (
    id integer NOT NULL,
    session_id integer,
    faction_id integer,
    faction_name text,
    policy_mode text,
    market_standard text,
    provenance_rule text,
    certification_rule text,
    royal_oversight text,
    rights_level integer,
    slave_trade_rep integer,
    notes text,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: faction_slave_policy_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.faction_slave_policy_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faction_slave_policy_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.faction_slave_policy_id_seq OWNED BY maya_rp.faction_slave_policy.id;


--
-- Name: faction_species_rights; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.faction_species_rights (
    id integer NOT NULL,
    session_id integer,
    faction_id integer,
    slavery_type text,
    citizenship text,
    purge_policy text,
    residence_allowed boolean,
    servitude_allowed boolean,
    notes text,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: faction_species_rights_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.faction_species_rights_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faction_species_rights_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.faction_species_rights_id_seq OWNED BY maya_rp.faction_species_rights.id;


--
-- Name: faction_trade_deals; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.faction_trade_deals (
    id integer NOT NULL,
    faction_a_id integer,
    faction_b_id integer,
    resource_type character varying(50),
    quantity integer,
    price numeric,
    duration_days integer,
    active boolean DEFAULT true,
    signed_at timestamp without time zone DEFAULT now()
);


--
-- Name: faction_trade_deals_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.faction_trade_deals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faction_trade_deals_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.faction_trade_deals_id_seq OWNED BY maya_rp.faction_trade_deals.id;


--
-- Name: factions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.factions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: factions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.factions_id_seq OWNED BY maya_rp.factions.id;


--
-- Name: family_relations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.family_relations (
    id integer NOT NULL,
    session_id integer NOT NULL,
    member_id integer NOT NULL,
    relation_type text NOT NULL,
    related_id integer NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT family_relations_relation_type_check CHECK ((relation_type = ANY (ARRAY['spouse'::text, 'sibling'::text, 'betrothed'::text, 'guardian'::text, 'cousin'::text])))
);


--
-- Name: family_relations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.family_relations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: family_relations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.family_relations_id_seq OWNED BY maya_rp.family_relations.id;


--
-- Name: fleet_formations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.fleet_formations (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    description text,
    bonus jsonb,
    available_for character varying(20) DEFAULT 'both'::character varying
);


--
-- Name: fleet_formations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.fleet_formations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fleet_formations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.fleet_formations_id_seq OWNED BY maya_rp.fleet_formations.id;


--
-- Name: fleet_members; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.fleet_members (
    id integer NOT NULL,
    fleet_id integer NOT NULL,
    ship_id integer NOT NULL,
    "position" integer DEFAULT 1 NOT NULL,
    assigned_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fleet_members_position_check CHECK ((("position" >= 1) AND ("position" <= 10)))
);


--
-- Name: fleet_members_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.fleet_members_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fleet_members_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.fleet_members_id_seq OWNED BY maya_rp.fleet_members.id;


--
-- Name: fleets; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.fleets (
    id integer NOT NULL,
    session_id integer NOT NULL,
    name text NOT NULL,
    formation text DEFAULT 'wall'::text NOT NULL,
    flagship_id integer,
    admiral_crew_id integer,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    role text,
    CONSTRAINT fleets_formation_check CHECK ((formation = ANY (ARRAY['wall'::text, 'crescent'::text, 'spearhead'::text, 'screen'::text, 'arrow'::text, 'scatter'::text]))),
    CONSTRAINT fleets_status_check CHECK ((status = ANY (ARRAY['active'::text, 'deployed'::text, 'rebuilding'::text, 'disbanded'::text])))
);


--
-- Name: fleets_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.fleets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fleets_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.fleets_id_seq OWNED BY maya_rp.fleets.id;


--
-- Name: global_modifiers; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.global_modifiers (
    id integer NOT NULL,
    modifier_type character varying(50) NOT NULL,
    value numeric NOT NULL,
    source_research_id integer,
    applied_at timestamp without time zone DEFAULT now()
);


--
-- Name: global_modifiers_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.global_modifiers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: global_modifiers_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.global_modifiers_id_seq OWNED BY maya_rp.global_modifiers.id;


--
-- Name: global_settings; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.global_settings (
    key character varying(50) NOT NULL,
    value text,
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: governance_projects; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.governance_projects (
    id integer NOT NULL,
    session_id integer NOT NULL,
    decree_id integer,
    project_type text NOT NULL,
    name text NOT NULL,
    description text,
    status text DEFAULT 'proposed'::text NOT NULL,
    progress_pct integer DEFAULT 0,
    resources_allocated jsonb DEFAULT '{}'::jsonb,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT governance_projects_progress_pct_check CHECK (((progress_pct >= 0) AND (progress_pct <= 100))),
    CONSTRAINT governance_projects_project_type_check CHECK ((project_type = ANY (ARRAY['military_buildup'::text, 'colony_expansion'::text, 'diplomatic_campaign'::text, 'covert_operation'::text, 'economic_reform'::text, 'welfare_program'::text, 'infrastructure'::text, 'education_initiative'::text, 'research_program'::text]))),
    CONSTRAINT governance_projects_status_check CHECK ((status = ANY (ARRAY['proposed'::text, 'approved'::text, 'active'::text, 'stalled'::text, 'completed'::text, 'cancelled'::text])))
);


--
-- Name: governance_projects_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.governance_projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: governance_projects_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.governance_projects_id_seq OWNED BY maya_rp.governance_projects.id;


--
-- Name: governor_applicants; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.governor_applicants (
    id integer NOT NULL,
    session_id integer DEFAULT 3 NOT NULL,
    name text NOT NULL,
    home_system text,
    occupation text,
    citizenship_years integer,
    admin_score integer,
    justice_score integer,
    economic_score integer,
    standing_score integer,
    security_score integer,
    total_score integer,
    status text DEFAULT 'applied'::text,
    created_at timestamp with time zone DEFAULT now(),
    loyalty_score integer,
    loyalty_improvable boolean,
    quirk text,
    assigned_system text,
    fit_score integer,
    home_territory_id integer,
    assigned_territory_id integer
);


--
-- Name: governor_applicants_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.governor_applicants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: governor_applicants_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.governor_applicants_id_seq OWNED BY maya_rp.governor_applicants.id;


--
-- Name: grand_plan; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.grand_plan (
    id integer NOT NULL,
    session_id integer NOT NULL,
    phase text NOT NULL,
    item_name text NOT NULL,
    item_type text NOT NULL,
    location text,
    sector text,
    status text DEFAULT 'planned'::text,
    cost_credits bigint DEFAULT 0,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    ministry text,
    CONSTRAINT grand_plan_item_type_check CHECK ((item_type = ANY (ARRAY['yard'::text, 'governorate'::text, 'military_base'::text, 'star_gate'::text, 'colony'::text, 'infrastructure'::text, 'research'::text, 'diplomacy'::text, 'intel'::text, 'ship_build'::text, 'military'::text, 'economic'::text])))
);


--
-- Name: grand_plan_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.grand_plan_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: grand_plan_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.grand_plan_id_seq OWNED BY maya_rp.grand_plan.id;


--
-- Name: guardrail_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.guardrail_log (
    id integer NOT NULL,
    test_type text NOT NULL,
    scene_type text,
    prompt_hash text NOT NULL,
    provider text NOT NULL,
    status text NOT NULL,
    image_url text,
    rejection_reason text,
    duration_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: guardrail_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.guardrail_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: guardrail_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.guardrail_log_id_seq OWNED BY maya_rp.guardrail_log.id;


--
-- Name: horror_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.horror_events (
    id integer NOT NULL,
    session_id integer NOT NULL,
    system_name text NOT NULL,
    horror_type text NOT NULL,
    stage integer DEFAULT 1,
    crew_lost integer DEFAULT 0,
    ships_lost integer DEFAULT 0,
    morale_delta integer DEFAULT 0,
    narrative text,
    triggered_at timestamp with time zone DEFAULT now(),
    territory_id integer,
    CONSTRAINT horror_events_horror_type_check CHECK ((horror_type = ANY (ARRAY['void_whisper'::text, 'reality_tear'::text, 'sleeper_awakened'::text, 'flesh_garden'::text, 'time_loop'::text, 'star_eater'::text, 'mind_plague'::text]))),
    CONSTRAINT horror_events_stage_check CHECK (((stage >= 1) AND (stage <= 5)))
);


--
-- Name: horror_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.horror_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: horror_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.horror_events_id_seq OWNED BY maya_rp.horror_events.id;


--
-- Name: ideology_state; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ideology_state (
    session_id integer NOT NULL,
    ideology text DEFAULT 'benevolent_democracy'::text,
    scores_jsonb jsonb DEFAULT '{}'::jsonb,
    set_at timestamp with time zone DEFAULT now()
);


--
-- Name: image_generations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.image_generations (
    id integer NOT NULL,
    prompt_id integer,
    provider text NOT NULL,
    model text,
    quality text DEFAULT 'medium'::text,
    size text DEFAULT '1024x1024'::text,
    image_path text,
    cost_estimate double precision DEFAULT 0.0,
    duration_ms integer DEFAULT 0,
    success boolean DEFAULT false,
    error_message text,
    generated_at timestamp with time zone DEFAULT now()
);


--
-- Name: image_generations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.image_generations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: image_generations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.image_generations_id_seq OWNED BY maya_rp.image_generations.id;


--
-- Name: image_prompts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.image_prompts (
    id integer NOT NULL,
    session_id integer,
    scene_type text NOT NULL,
    subject_name text,
    prompt_full text NOT NULL,
    prompt_variables jsonb DEFAULT '{}'::jsonb,
    moderator_applied boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT image_prompts_scene_type_check CHECK ((scene_type = ANY (ARRAY['character-portrait'::text, 'battle-scene'::text, 'planet-landscape'::text, 'cosmic-horror'::text, 'intimate-moment'::text, 'spaceship-blueprint'::text])))
);


--
-- Name: image_prompts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.image_prompts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: image_prompts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.image_prompts_id_seq OWNED BY maya_rp.image_prompts.id;


--
-- Name: incoming_raids; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.incoming_raids (
    id integer NOT NULL,
    session_id integer NOT NULL,
    faction_name text NOT NULL,
    target_system text NOT NULL,
    enemy_power integer DEFAULT 500,
    ticks_remaining integer DEFAULT 3,
    detected boolean DEFAULT false,
    sensor_level integer DEFAULT 0,
    player_responded boolean DEFAULT false,
    response_action text,
    created_at timestamp with time zone DEFAULT now(),
    target_territory_id integer
);


--
-- Name: incoming_raids_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.incoming_raids_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incoming_raids_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.incoming_raids_id_seq OWNED BY maya_rp.incoming_raids.id;


--
-- Name: infestation_instances; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.infestation_instances (
    id integer NOT NULL,
    session_id integer,
    sector_id integer,
    territory_id integer,
    stage_id integer,
    biomass integer DEFAULT 100,
    spread_progress integer DEFAULT 0,
    discovered boolean DEFAULT false,
    discovered_at timestamp without time zone,
    contained boolean DEFAULT false,
    containment_level integer DEFAULT 0,
    last_spread timestamp without time zone,
    created_at timestamp without time zone DEFAULT now(),
    destroyed_at timestamp without time zone,
    status character varying(20) DEFAULT 'active'::character varying
);


--
-- Name: infestation_instances_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.infestation_instances_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: infestation_instances_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.infestation_instances_id_seq OWNED BY maya_rp.infestation_instances.id;


--
-- Name: infestation_stages; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.infestation_stages (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    description text,
    spread_rate numeric DEFAULT 1.0,
    consumption_rate numeric DEFAULT 1.0,
    threat_level integer DEFAULT 1,
    visibility character varying(20),
    requires_containment boolean DEFAULT false
);


--
-- Name: infestation_stages_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.infestation_stages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: infestation_stages_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.infestation_stages_id_seq OWNED BY maya_rp.infestation_stages.id;


--
-- Name: sectors; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.sectors (
    id integer NOT NULL,
    session_id integer,
    name character varying(100) NOT NULL,
    x_coord integer NOT NULL,
    y_coord integer NOT NULL,
    star_type character varying(50) DEFAULT 'main_sequence'::character varying,
    resource_richness double precision DEFAULT 1.0,
    hazard_level double precision DEFAULT 0.0,
    controlled_by character varying(100)
);


--
-- Name: infestation_threats; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.infestation_threats AS
 SELECT ii.id,
    ii.sector_id,
    s.name AS sector_name,
    ii.territory_id,
    t.system_name AS territory_name,
    st.name AS stage,
    st.threat_level,
    ii.biomass,
    ii.spread_progress,
    ii.contained,
    ii.containment_level,
    ii.discovered,
    ii.status,
    ii.created_at
   FROM (((maya_rp.infestation_instances ii
     LEFT JOIN maya_rp.sectors s ON ((s.id = ii.sector_id)))
     LEFT JOIN maya_rp.territory t ON ((t.id = ii.territory_id)))
     JOIN maya_rp.infestation_stages st ON ((st.id = ii.stage_id)))
  WHERE ((ii.status)::text <> ALL ((ARRAY['destroyed'::character varying, 'eradicated'::character varying])::text[]));


--
-- Name: infrastructure_instances; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.infrastructure_instances (
    id integer NOT NULL,
    session_id integer,
    infrastructure_type_id integer,
    territory_id integer,
    sector_id integer,
    name character varying(100) NOT NULL,
    level integer DEFAULT 1,
    status character varying(20) DEFAULT 'active'::character varying,
    built_at timestamp without time zone DEFAULT now(),
    last_upgrade timestamp without time zone,
    upgrades_applied jsonb DEFAULT '[]'::jsonb,
    production_bonus numeric DEFAULT 1.0
);


--
-- Name: infrastructure_instances_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.infrastructure_instances_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: infrastructure_instances_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.infrastructure_instances_id_seq OWNED BY maya_rp.infrastructure_instances.id;


--
-- Name: infrastructure_types; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.infrastructure_types (
    id integer NOT NULL,
    category character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    fantasy_tier character varying(20),
    build_cost_credits integer,
    build_cost_resources jsonb,
    upkeep_credits integer,
    upkeep_resources jsonb,
    construction_time_days integer,
    effects jsonb,
    required_tech character varying(100),
    size integer DEFAULT 1,
    slots_used integer DEFAULT 1
);


--
-- Name: infrastructure_overview; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.infrastructure_overview AS
 SELECT ii.id,
    ii.name,
    it.name AS type_name,
    it.category,
    it.fantasy_tier,
    ii.level,
    ii.status,
    t.system_name AS territory_name,
    s.name AS sector_name,
    ii.built_at,
    ii.upgrades_applied
   FROM (((maya_rp.infrastructure_instances ii
     JOIN maya_rp.infrastructure_types it ON ((it.id = ii.infrastructure_type_id)))
     LEFT JOIN maya_rp.territory t ON ((t.id = ii.territory_id)))
     LEFT JOIN maya_rp.sectors s ON ((s.id = ii.sector_id)));


--
-- Name: infrastructure_production; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.infrastructure_production (
    id integer NOT NULL,
    infrastructure_id integer,
    resource_type character varying(50) NOT NULL,
    amount_produced integer DEFAULT 0,
    produced_at timestamp without time zone DEFAULT now()
);


--
-- Name: infrastructure_production_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.infrastructure_production_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: infrastructure_production_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.infrastructure_production_id_seq OWNED BY maya_rp.infrastructure_production.id;


--
-- Name: infrastructure_types_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.infrastructure_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: infrastructure_types_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.infrastructure_types_id_seq OWNED BY maya_rp.infrastructure_types.id;


--
-- Name: intel_reports; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.intel_reports (
    id integer NOT NULL,
    recipient_faction_id integer,
    source_faction_id integer,
    report_type character varying(50),
    content text,
    generated_at timestamp without time zone DEFAULT now(),
    expires_at timestamp without time zone,
    seen boolean DEFAULT false
);


--
-- Name: intel_reports_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.intel_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: intel_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.intel_reports_id_seq OWNED BY maya_rp.intel_reports.id;


--
-- Name: interrogation_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.interrogation_log (
    id integer NOT NULL,
    prisoner_id integer NOT NULL,
    session_id integer NOT NULL,
    method text NOT NULL,
    ship_id integer,
    secrecy_level text DEFAULT 'hidden'::text NOT NULL,
    witnesses jsonb DEFAULT '[]'::jsonb,
    companion_reactions jsonb DEFAULT '{}'::jsonb,
    intel_yield integer DEFAULT 0,
    moral_cost integer DEFAULT 0,
    brutality_cost integer DEFAULT 0,
    reputation_delta jsonb DEFAULT '{}'::jsonb,
    prisoner_broken boolean DEFAULT false,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT interrogation_log_method_check CHECK ((method = ANY (ARRAY['standard'::text, 'enhanced'::text, 'brutal'::text]))),
    CONSTRAINT interrogation_log_secrecy_level_check CHECK ((secrecy_level = ANY (ARRAY['public'::text, 'hidden'::text, 'witnessed'::text])))
);


--
-- Name: interrogation_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.interrogation_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: interrogation_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.interrogation_log_id_seq OWNED BY maya_rp.interrogation_log.id;


--
-- Name: intimacy_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.intimacy_events (
    id integer NOT NULL,
    session_id integer NOT NULL,
    character_id integer NOT NULL,
    event_type text NOT NULL,
    intensity integer DEFAULT 1,
    narrative text,
    bond_delta integer DEFAULT 0,
    dream_essence_gain integer DEFAULT 5,
    triggered_at timestamp with time zone DEFAULT now(),
    CONSTRAINT intimacy_events_event_type_check CHECK ((event_type = ANY (ARRAY['embrace'::text, 'kiss'::text, 'cuddle'::text, 'confession'::text, 'shared_night'::text, 'missionary'::text, 'cowgirl'::text, 'reverse_cowgirl'::text, 'doggystyle'::text, 'mount'::text, 'pile_drive'::text, 'standing'::text, 'against_wall'::text, 'oral_give'::text, 'oral_receive'::text, 'sixty_nine'::text, 'dominate'::text, 'submit'::text, 'bondage'::text, 'edge'::text, 'ritual'::text, 'afterglow'::text, 'jealousy_scene'::text, 'intimacy'::text, 'scene_roll'::text, 'aftercare'::text, 'peck'::text, 'sandwich'::text, 'doggy'::text, 'piledriver'::text, 'pool_deck'::text]))),
    CONSTRAINT intimacy_events_intensity_check CHECK ((intensity >= 1))
);


--
-- Name: intimacy_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.intimacy_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: intimacy_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.intimacy_events_id_seq OWNED BY maya_rp.intimacy_events.id;


--
-- Name: investigation_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.investigation_log (
    id integer NOT NULL,
    investigation_id integer NOT NULL,
    session_id integer NOT NULL,
    entry_type text NOT NULL,
    clue_id integer,
    description text NOT NULL,
    npc_name text,
    companion_assist boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT investigation_log_entry_type_check CHECK ((entry_type = ANY (ARRAY['clue_found'::text, 'deduction'::text, 'interrogation'::text, 'revelation'::text, 'dead_end'::text, 'witness'::text])))
);


--
-- Name: investigation_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.investigation_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: investigation_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.investigation_log_id_seq OWNED BY maya_rp.investigation_log.id;


--
-- Name: investigations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.investigations (
    id integer NOT NULL,
    session_id integer NOT NULL,
    title text NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    phase text DEFAULT 'observe'::text NOT NULL,
    clues_found integer DEFAULT 0,
    deductions_made integer DEFAULT 0,
    summary text,
    created_at timestamp with time zone DEFAULT now(),
    solved_at timestamp with time zone,
    CONSTRAINT investigations_phase_check CHECK ((phase = ANY (ARRAY['observe'::text, 'analyze'::text, 'deduce'::text, 'revelation'::text, 'closed'::text]))),
    CONSTRAINT investigations_status_check CHECK ((status = ANY (ARRAY['open'::text, 'active'::text, 'stalled'::text, 'solved'::text, 'cold'::text])))
);


--
-- Name: investigations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.investigations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: investigations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.investigations_id_seq OWNED BY maya_rp.investigations.id;


--
-- Name: jealousy_states; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.jealousy_states (
    id integer NOT NULL,
    session_id integer NOT NULL,
    character_id integer NOT NULL,
    rival_id integer NOT NULL,
    jealousy_level integer DEFAULT 0,
    last_trigger timestamp with time zone,
    CONSTRAINT jealousy_states_jealousy_level_check CHECK (((jealousy_level >= 0) AND (jealousy_level <= 100)))
);


--
-- Name: jealousy_states_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.jealousy_states_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: jealousy_states_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.jealousy_states_id_seq OWNED BY maya_rp.jealousy_states.id;


--
-- Name: leader_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.leader_events (
    id integer NOT NULL,
    leader_id integer,
    event_type character varying(50),
    happened_at timestamp without time zone DEFAULT now(),
    details jsonb,
    new_leader_id integer
);


--
-- Name: leader_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.leader_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: leader_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.leader_events_id_seq OWNED BY maya_rp.leader_events.id;


--
-- Name: leaders_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.leaders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: leaders_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.leaders_id_seq OWNED BY maya_rp.leaders.id;


--
-- Name: legendary_artifacts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.legendary_artifacts (
    id integer NOT NULL,
    session_id integer,
    name character varying(200) NOT NULL,
    artifact_type character varying(50) NOT NULL,
    rarity character varying(20) NOT NULL,
    power_level double precision DEFAULT 1.0,
    effects jsonb DEFAULT '[]'::jsonb,
    lore_text text,
    origin_civilization character varying(100),
    origin_age character varying(50),
    current_location_type character varying(50),
    current_location_id integer,
    current_owner character varying(100),
    discovered_at timestamp with time zone
);


--
-- Name: legendary_artifacts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.legendary_artifacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: legendary_artifacts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.legendary_artifacts_id_seq OWNED BY maya_rp.legendary_artifacts.id;


--
-- Name: legio_structure; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.legio_structure (
    id integer NOT NULL,
    session_id integer NOT NULL,
    legio_id text NOT NULL,
    legio_name text NOT NULL,
    direction text,
    general_id integer,
    century_num integer NOT NULL,
    century_type text NOT NULL,
    cohort_num integer DEFAULT 10 NOT NULL,
    ships_per_cohort integer DEFAULT 100 NOT NULL,
    status text DEFAULT 'building'::text,
    created_at timestamp with time zone DEFAULT now(),
    century_tier integer DEFAULT 4,
    CONSTRAINT legio_structure_century_type_check CHECK ((century_type = ANY (ARRAY['elite'::text, 'standard'::text])))
);


--
-- Name: legio_structure_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.legio_structure_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: legio_structure_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.legio_structure_id_seq OWNED BY maya_rp.legio_structure.id;


--
-- Name: legion_snapshot; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.legion_snapshot (
    session_id integer,
    snapshot_at timestamp without time zone DEFAULT now(),
    data jsonb
);


--
-- Name: location_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.location_catalog (
    name text NOT NULL,
    location_type text,
    default_lighting text,
    default_sound text,
    default_smell text,
    atmosphere text
);


--
-- Name: locations; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.locations (
    id integer NOT NULL,
    session_id integer NOT NULL,
    name text NOT NULL,
    location_type text,
    description text,
    faction_control text,
    mood text,
    secrets jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: locations_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.locations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: locations_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.locations_id_seq OWNED BY maya_rp.locations.id;


--
-- Name: material_stockpiles; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.material_stockpiles (
    id integer NOT NULL,
    session_id integer,
    colony_id integer,
    material_name text NOT NULL,
    quantity numeric DEFAULT 0,
    reserved numeric DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: material_stockpiles_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.material_stockpiles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: material_stockpiles_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.material_stockpiles_id_seq OWNED BY maya_rp.material_stockpiles.id;


--
-- Name: materials; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.materials (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    base_value double precision DEFAULT 1.0,
    tech_tier integer DEFAULT 1
);


--
-- Name: materials_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.materials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: materials_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.materials_id_seq OWNED BY maya_rp.materials.id;


--
-- Name: megastructure_construction; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.megastructure_construction (
    id integer NOT NULL,
    session_id integer,
    megastructure_type_id integer,
    sector_id integer,
    territory_id integer,
    current_phase integer DEFAULT 1,
    progress_pct integer DEFAULT 0,
    started_at timestamp without time zone DEFAULT now(),
    estimated_completion timestamp without time zone,
    status character varying(20) DEFAULT 'construction'::character varying,
    resources_allocated jsonb
);


--
-- Name: megastructure_construction_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.megastructure_construction_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: megastructure_construction_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.megastructure_construction_id_seq OWNED BY maya_rp.megastructure_construction.id;


--
-- Name: megastructure_types; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.megastructure_types (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    fantasy_tier character varying(20),
    construction_phases jsonb,
    total_cost_credits bigint,
    total_cost_resources jsonb,
    benefits jsonb,
    research_required character varying(100),
    unlocks character varying(100),
    size integer DEFAULT 1
);


--
-- Name: megastructure_status; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.megastructure_status AS
 SELECT mc.id,
    mt.name,
    mt.fantasy_tier,
    mc.current_phase,
    mc.progress_pct,
    mc.estimated_completion,
    mc.status,
    s.name AS sector_name,
    t.system_name AS territory_name
   FROM (((maya_rp.megastructure_construction mc
     JOIN maya_rp.megastructure_types mt ON ((mt.id = mc.megastructure_type_id)))
     LEFT JOIN maya_rp.sectors s ON ((s.id = mc.sector_id)))
     LEFT JOIN maya_rp.territory t ON ((t.id = mc.territory_id)));


--
-- Name: megastructure_types_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.megastructure_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: megastructure_types_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.megastructure_types_id_seq OWNED BY maya_rp.megastructure_types.id;


--
-- Name: migration_hashes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.migration_hashes (
    filename text NOT NULL,
    sha256 text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: migration_versions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.migration_versions (
    id integer NOT NULL,
    version character varying(20) NOT NULL,
    applied_at timestamp with time zone DEFAULT now(),
    checksum text
);


--
-- Name: migration_versions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.migration_versions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: migration_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.migration_versions_id_seq OWNED BY maya_rp.migration_versions.id;


--
-- Name: military_expenditure; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.military_expenditure (
    id integer NOT NULL,
    territory_id integer,
    campaign_id integer,
    alloy_consumed integer,
    fuel_consumed integer,
    credits_consumed integer,
    population_drafted integer,
    started_at timestamp without time zone DEFAULT now(),
    ended_at timestamp without time zone
);


--
-- Name: military_expenditure_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.military_expenditure_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: military_expenditure_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.military_expenditure_id_seq OWNED BY maya_rp.military_expenditure.id;


--
-- Name: modules; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.modules (
    id integer NOT NULL,
    name text NOT NULL,
    category text NOT NULL,
    effect_type text NOT NULL,
    effect_value double precision NOT NULL,
    grade integer DEFAULT 1 NOT NULL,
    tier_min integer NOT NULL,
    tier_max integer DEFAULT 8 NOT NULL,
    cost_alloys bigint DEFAULT 0 NOT NULL,
    cost_credits bigint DEFAULT 0 NOT NULL,
    special_rules jsonb DEFAULT '{}'::jsonb
);


--
-- Name: modules_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.modules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: modules_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.modules_id_seq OWNED BY maya_rp.modules.id;


--
-- Name: morale_history; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.morale_history (
    id integer NOT NULL,
    session_id integer NOT NULL,
    ship_id integer,
    fleet_wide boolean DEFAULT false,
    morale_before integer NOT NULL,
    morale_after integer NOT NULL,
    cause text NOT NULL,
    crew_affected jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: morale_history_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.morale_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: morale_history_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.morale_history_id_seq OWNED BY maya_rp.morale_history.id;


--
-- Name: morality_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.morality_log (
    id integer NOT NULL,
    session_id integer NOT NULL,
    character_id integer,
    action text NOT NULL,
    morality_delta integer DEFAULT 0,
    new_score integer DEFAULT 0,
    narrative text,
    logged_at timestamp with time zone DEFAULT now()
);


--
-- Name: morality_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.morality_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: morality_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.morality_log_id_seq OWNED BY maya_rp.morality_log.id;


--
-- Name: mystery_templates; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.mystery_templates (
    id integer NOT NULL,
    name text NOT NULL,
    type text NOT NULL,
    phases jsonb DEFAULT '["observe", "analyze", "deduce", "revelation"]'::jsonb NOT NULL,
    min_clues_for_deduction integer DEFAULT 3,
    companion_expertise jsonb
);


--
-- Name: mystery_templates_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.mystery_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mystery_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.mystery_templates_id_seq OWNED BY maya_rp.mystery_templates.id;


--
-- Name: narrative_hooks; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.narrative_hooks (
    id integer NOT NULL,
    session_id integer,
    hook_type character varying(50),
    description text,
    trigger_conditions jsonb,
    status character varying(20) DEFAULT 'pending'::character varying,
    created_at timestamp without time zone DEFAULT now(),
    resolved_at timestamp without time zone,
    resolution text
);


--
-- Name: narrative_hooks_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.narrative_hooks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: narrative_hooks_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.narrative_hooks_id_seq OWNED BY maya_rp.narrative_hooks.id;


--
-- Name: narrative_pacing; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.narrative_pacing (
    session_id integer NOT NULL,
    mode character varying(20) DEFAULT 'downtime'::character varying,
    entered_at_game_day integer DEFAULT 0,
    tension integer DEFAULT 0,
    scenes_in_mode integer DEFAULT 0,
    last_transition_reason text,
    mode_history jsonb DEFAULT '[]'::jsonb,
    CONSTRAINT narrative_pacing_tension_check CHECK (((tension >= 0) AND (tension <= 10)))
);


--
-- Name: narrative_seeds; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.narrative_seeds (
    id integer NOT NULL,
    session_id integer,
    seed_type text,
    content text,
    planted_at_game_day integer,
    payoff_condition text,
    payoff_event_template text,
    payoff_game_day integer,
    status text DEFAULT 'planted'::text,
    foreshadow_count integer DEFAULT 0,
    max_foreshadows integer DEFAULT 3
);


--
-- Name: narrative_seeds_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.narrative_seeds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: narrative_seeds_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.narrative_seeds_id_seq OWNED BY maya_rp.narrative_seeds.id;


--
-- Name: narrator_cost_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.narrator_cost_log (
    id integer NOT NULL,
    session_id integer NOT NULL,
    provider text NOT NULL,
    event_type text,
    prompt_tokens integer DEFAULT 0,
    output_tokens integer DEFAULT 0,
    latency_ms integer DEFAULT 0,
    estimated_cost_cents double precision DEFAULT 0,
    success boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: narrator_cost_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.narrator_cost_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: narrator_cost_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.narrator_cost_log_id_seq OWNED BY maya_rp.narrator_cost_log.id;


--
-- Name: news_articles; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.news_articles (
    id integer NOT NULL,
    session_id integer,
    tick_number integer NOT NULL,
    headline character varying(200) NOT NULL,
    body text,
    category character varying(50) NOT NULL,
    faction_bias character varying(100),
    importance integer DEFAULT 5,
    read boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    game_day integer
);


--
-- Name: news_articles_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.news_articles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: news_articles_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.news_articles_id_seq OWNED BY maya_rp.news_articles.id;


--
-- Name: novel_chunks; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.novel_chunks (
    id integer NOT NULL,
    session_id integer DEFAULT 3,
    book text NOT NULL,
    part text,
    chapter text,
    chunk_index integer NOT NULL,
    chunk_text text NOT NULL,
    embedding public.vector(768),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: novel_chunks_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.novel_chunks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: novel_chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.novel_chunks_id_seq OWNED BY maya_rp.novel_chunks.id;


--
-- Name: npc_internal_state; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.npc_internal_state (
    character_id integer NOT NULL,
    session_id integer NOT NULL,
    personal_morale integer DEFAULT 50,
    personal_fear integer DEFAULT 0,
    personal_loyalty integer DEFAULT 50,
    current_mood character varying(20) DEFAULT 'stable'::character varying,
    current_concern text,
    relationship_with_player character varying(20) DEFAULT 'neutral'::character varying,
    unspoken_opinion text,
    last_reaction_event character varying(50)
);


--
-- Name: npc_offscreen_interactions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.npc_offscreen_interactions (
    id integer NOT NULL,
    session_id integer,
    character_a integer,
    character_b integer,
    interaction_type character varying(30),
    description text,
    discovered boolean DEFAULT false,
    game_day integer
);


--
-- Name: npc_offscreen_interactions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.npc_offscreen_interactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: npc_offscreen_interactions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.npc_offscreen_interactions_id_seq OWNED BY maya_rp.npc_offscreen_interactions.id;


--
-- Name: objectives; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.objectives (
    id integer NOT NULL,
    session_id integer DEFAULT 1 NOT NULL,
    title text NOT NULL,
    objective_type text,
    status text DEFAULT 'active'::text NOT NULL,
    priority integer DEFAULT 0,
    progress_pct integer DEFAULT 0
);


--
-- Name: objectives_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.objectives_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: objectives_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.objectives_id_seq OWNED BY maya_rp.objectives.id;


--
-- Name: pirate_activities; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_activities (
    id integer NOT NULL,
    trade_route_id integer,
    pirate_faction_id integer,
    loot_amount integer,
    happened_at timestamp without time zone DEFAULT now()
);


--
-- Name: pirate_activities_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_activities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_activities_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_activities_id_seq OWNED BY maya_rp.pirate_activities.id;


--
-- Name: pirate_alerts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_alerts (
    id integer NOT NULL,
    session_id integer,
    message text NOT NULL,
    severity integer DEFAULT 1,
    read boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: pirate_alerts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_alerts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_alerts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_alerts_id_seq OWNED BY maya_rp.pirate_alerts.id;


--
-- Name: pirate_artifacts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_artifacts (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    rarity character varying(20),
    effect jsonb,
    drop_from character varying(50)
);


--
-- Name: pirate_artifacts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_artifacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_artifacts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_artifacts_id_seq OWNED BY maya_rp.pirate_artifacts.id;


--
-- Name: pirate_bases; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_bases (
    id integer NOT NULL,
    faction_id integer,
    system_id integer,
    name character varying(100) NOT NULL,
    hidden boolean DEFAULT true,
    defenses integer DEFAULT 50,
    treasury bigint DEFAULT 500000,
    status character varying(20) DEFAULT 'active'::character varying
);


--
-- Name: pirate_bases_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_bases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_bases_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_bases_id_seq OWNED BY maya_rp.pirate_bases.id;


--
-- Name: pirate_bounties; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_bounties (
    id integer NOT NULL,
    pirate_faction_id integer,
    bounty_amount integer DEFAULT 50000,
    last_updated timestamp without time zone DEFAULT now(),
    claimed_by integer
);


--
-- Name: pirate_bounties_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_bounties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_bounties_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_bounties_id_seq OWNED BY maya_rp.pirate_bounties.id;


--
-- Name: pirate_extortion; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_extortion (
    id integer NOT NULL,
    pirate_faction_id integer,
    target_faction_id integer,
    target_territory_id integer,
    demand_credits integer,
    demand_resources jsonb,
    deadline timestamp without time zone,
    paid boolean DEFAULT false,
    responded boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now(),
    resolved_at timestamp without time zone
);


--
-- Name: pirate_extortion_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_extortion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_extortion_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_extortion_id_seq OWNED BY maya_rp.pirate_extortion.id;


--
-- Name: pirate_fleet_templates; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_fleet_templates (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    composition jsonb,
    total_power integer,
    threat_level character varying(20)
);


--
-- Name: pirate_fleet_templates_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_fleet_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_fleet_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_fleet_templates_id_seq OWNED BY maya_rp.pirate_fleet_templates.id;


--
-- Name: pirate_loot_tables; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_loot_tables (
    id integer NOT NULL,
    threat_level character varying(20) NOT NULL,
    loot_pool jsonb NOT NULL,
    drop_chance numeric DEFAULT 0.8
);


--
-- Name: pirate_loot_tables_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_loot_tables_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_loot_tables_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_loot_tables_id_seq OWNED BY maya_rp.pirate_loot_tables.id;


--
-- Name: pirate_raids; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_raids (
    id integer NOT NULL,
    pirate_faction_id integer,
    target_faction_id integer,
    target_territory_id integer,
    target_trade_route_id integer,
    raid_type character varying(50) NOT NULL,
    loot_credits integer DEFAULT 0,
    loot_resources jsonb,
    damage_dealt integer DEFAULT 0,
    started_at timestamp without time zone DEFAULT now(),
    ended_at timestamp without time zone,
    outcome character varying(20),
    description text,
    aggressor_ship_id integer,
    player_casualties integer DEFAULT 0,
    loot_items jsonb,
    player_earnings integer DEFAULT 0,
    captured_ship_id integer
);


--
-- Name: pirate_raids_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_raids_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_raids_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_raids_id_seq OWNED BY maya_rp.pirate_raids.id;


--
-- Name: pirate_salvage_templates; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_salvage_templates (
    id integer NOT NULL,
    ship_class character varying(50) NOT NULL,
    salvage_pool jsonb NOT NULL,
    capture_chance numeric DEFAULT 0.3
);


--
-- Name: pirate_salvage_templates_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_salvage_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_salvage_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_salvage_templates_id_seq OWNED BY maya_rp.pirate_salvage_templates.id;


--
-- Name: pirate_ship_classes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_ship_classes (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    hull integer NOT NULL,
    shield integer NOT NULL,
    weapons integer NOT NULL,
    speed integer NOT NULL,
    evasion numeric DEFAULT 0.1,
    combat_rating integer NOT NULL,
    cost_to_build integer,
    description text
);


--
-- Name: pirate_ship_classes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_ship_classes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_ship_classes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_ship_classes_id_seq OWNED BY maya_rp.pirate_ship_classes.id;


--
-- Name: pirate_zones; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pirate_zones (
    id integer NOT NULL,
    system_id integer,
    danger_level integer DEFAULT 3,
    last_patrol timestamp without time zone,
    active boolean DEFAULT true,
    protected boolean DEFAULT false NOT NULL
);


--
-- Name: pirate_zones_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pirate_zones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pirate_zones_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pirate_zones_id_seq OWNED BY maya_rp.pirate_zones.id;


--
-- Name: planet_features; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.planet_features (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    planet_type character varying(50),
    description text,
    effect jsonb,
    rarity character varying(20) DEFAULT 'common'::character varying
);


--
-- Name: planet_features_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.planet_features_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: planet_features_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.planet_features_id_seq OWNED BY maya_rp.planet_features.id;


--
-- Name: planet_population; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.planet_population (
    id integer NOT NULL,
    session_id integer NOT NULL,
    planet_id integer NOT NULL,
    species_id integer,
    species_name text NOT NULL,
    count bigint DEFAULT 0 NOT NULL,
    pct numeric(6,2) DEFAULT 0,
    dominant boolean DEFAULT false,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: planet_population_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.planet_population_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: planet_population_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.planet_population_id_seq OWNED BY maya_rp.planet_population.id;


--
-- Name: planet_types_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.planet_types_catalog (
    name character varying(50) NOT NULL,
    description text,
    habitability_min numeric DEFAULT 0,
    habitability_max numeric DEFAULT 100,
    special_events text[],
    resource_modifiers jsonb DEFAULT '{}'::jsonb,
    rarity character varying(20) DEFAULT 'common'::character varying
);


--
-- Name: planets; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.planets (
    id integer NOT NULL,
    session_id integer DEFAULT 1 NOT NULL,
    name text NOT NULL,
    system_name text,
    diameter_km integer,
    gravity_g double precision,
    atmosphere text,
    water_pct integer,
    habitability_score integer,
    biosphere text,
    status text DEFAULT 'unexplored'::text NOT NULL,
    habitability integer DEFAULT 0,
    terraformable boolean DEFAULT true,
    planet_type character varying(50),
    features jsonb DEFAULT '[]'::jsonb,
    surveyed boolean DEFAULT false,
    resource_modifiers jsonb DEFAULT '{}'::jsonb,
    territory_id integer,
    population bigint DEFAULT 0,
    governor_name text,
    is_capital boolean DEFAULT false,
    max_population bigint DEFAULT 0
);


--
-- Name: planets_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.planets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: planets_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.planets_id_seq OWNED BY maya_rp.planets.id;


--
-- Name: player_action_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.player_action_catalog (
    id integer NOT NULL,
    action_type text NOT NULL,
    condition text DEFAULT 'none'::text,
    live_chance integer DEFAULT 50,
    outcome_live text DEFAULT ''::text,
    outcome_death text DEFAULT ''::text,
    description text DEFAULT ''::text
);


--
-- Name: player_action_catalog_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.player_action_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: player_action_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.player_action_catalog_id_seq OWNED BY maya_rp.player_action_catalog.id;


--
-- Name: player_action_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.player_action_log (
    id integer NOT NULL,
    session_id integer,
    action_category character varying(30),
    count integer DEFAULT 1,
    raw_input text,
    recorded_at timestamp with time zone DEFAULT now()
);


--
-- Name: player_action_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.player_action_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: player_action_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.player_action_log_id_seq OWNED BY maya_rp.player_action_log.id;


--
-- Name: player_context; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.player_context (
    session_id integer NOT NULL,
    current_focus character varying(50),
    mood character varying(50),
    last_action character varying(100),
    last_action_time timestamp without time zone,
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: player_trades; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.player_trades (
    id integer NOT NULL,
    session_id integer,
    commodity_id integer,
    trade_type character varying(10) NOT NULL,
    quantity double precision NOT NULL,
    unit_price double precision NOT NULL,
    total_cost double precision NOT NULL,
    traded_at timestamp with time zone DEFAULT now()
);


--
-- Name: player_trades_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.player_trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: player_trades_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.player_trades_id_seq OWNED BY maya_rp.player_trades.id;


--
-- Name: policy_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.policy_catalog (
    id integer NOT NULL,
    session_id integer,
    category text,
    policy_key text,
    policy_name text,
    options jsonb,
    default_option text,
    description text,
    effects jsonb,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: policy_catalog_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.policy_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: policy_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.policy_catalog_id_seq OWNED BY maya_rp.policy_catalog.id;


--
-- Name: policy_registry; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.policy_registry (
    id integer NOT NULL,
    source text NOT NULL,
    policy_name text NOT NULL,
    condition text DEFAULT 'any'::text,
    action text NOT NULL,
    outcome text DEFAULT ''::text,
    policy_text text DEFAULT ''::text
);


--
-- Name: policy_registry_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.policy_registry_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: policy_registry_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.policy_registry_id_seq OWNED BY maya_rp.policy_registry.id;


--
-- Name: political_factions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.political_factions (
    id integer NOT NULL,
    faction_id integer,
    name character varying(100) NOT NULL,
    ideology character varying(50),
    influence integer DEFAULT 10,
    leader_id integer,
    loyalty integer DEFAULT 50,
    demands jsonb
);


--
-- Name: political_factions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.political_factions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: political_factions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.political_factions_id_seq OWNED BY maya_rp.political_factions.id;


--
-- Name: population_sentiment; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.population_sentiment (
    id integer NOT NULL,
    session_id integer NOT NULL,
    territory_id integer NOT NULL,
    faction_id integer,
    faction_name text NOT NULL,
    sentiment integer DEFAULT 0 NOT NULL,
    approval integer DEFAULT 0 NOT NULL,
    fear integer DEFAULT 0 NOT NULL,
    trust integer DEFAULT 0 NOT NULL,
    bias integer DEFAULT 0 NOT NULL,
    last_shift integer DEFAULT 0 NOT NULL,
    last_shift_reason text,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: population_sentiment_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.population_sentiment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: population_sentiment_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.population_sentiment_id_seq OWNED BY maya_rp.population_sentiment.id;


--
-- Name: port_types; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.port_types (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    category character varying(20),
    build_cost_credits integer,
    build_cost_resources jsonb,
    upkeep_credits integer,
    benefits jsonb,
    upgrades jsonb,
    description text
);


--
-- Name: ports; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ports (
    id integer NOT NULL,
    session_id integer,
    territory_id integer,
    port_type_id integer,
    name character varying(100) NOT NULL,
    level integer DEFAULT 1,
    built_at timestamp without time zone DEFAULT now(),
    status character varying(20) DEFAULT 'active'::character varying,
    upgrades_applied jsonb DEFAULT '[]'::jsonb
);


--
-- Name: port_overview; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.port_overview AS
 SELECT p.id,
    p.name,
    pt.name AS port_type,
    pt.category,
    p.level,
    p.status,
    t.system_name AS territory_name,
    p.built_at,
    p.upgrades_applied
   FROM ((maya_rp.ports p
     JOIN maya_rp.port_types pt ON ((pt.id = p.port_type_id)))
     JOIN maya_rp.territory t ON ((t.id = p.territory_id)));


--
-- Name: port_types_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.port_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: port_types_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.port_types_id_seq OWNED BY maya_rp.port_types.id;


--
-- Name: port_upgrades; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.port_upgrades (
    id integer NOT NULL,
    port_id integer,
    upgrade_name character varying(100),
    applied_at timestamp without time zone DEFAULT now(),
    cost_credits integer,
    cost_resources jsonb
);


--
-- Name: port_upgrades_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.port_upgrades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: port_upgrades_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.port_upgrades_id_seq OWNED BY maya_rp.port_upgrades.id;


--
-- Name: ports_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ports_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ports_id_seq OWNED BY maya_rp.ports.id;


--
-- Name: pregnancies; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.pregnancies (
    id integer NOT NULL,
    session_id integer NOT NULL,
    mother_id integer,
    mother_name text NOT NULL,
    father_name text DEFAULT 'King Izzat'::text,
    conceived_game_day integer NOT NULL,
    due_game_day integer NOT NULL,
    gestation_days integer DEFAULT 270 NOT NULL,
    trimester integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    baby_name text,
    baby_gender text,
    notes text,
    birthed_game_day integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: pregnancies_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.pregnancies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pregnancies_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.pregnancies_id_seq OWNED BY maya_rp.pregnancies.id;


--
-- Name: price_history; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.price_history (
    id integer NOT NULL,
    commodity_id integer,
    tick_number integer NOT NULL,
    price double precision NOT NULL,
    volume double precision DEFAULT 0
);


--
-- Name: price_history_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.price_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: price_history_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.price_history_id_seq OWNED BY maya_rp.price_history.id;


--
-- Name: prisoner_intel_pipeline; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.prisoner_intel_pipeline (
    id integer NOT NULL,
    prisoner_id integer,
    investigation_id integer,
    intel_text text NOT NULL,
    converted_to_clue boolean DEFAULT false,
    clue_id integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: prisoner_intel_pipeline_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.prisoner_intel_pipeline_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prisoner_intel_pipeline_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.prisoner_intel_pipeline_id_seq OWNED BY maya_rp.prisoner_intel_pipeline.id;


--
-- Name: prisoners; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.prisoners (
    id integer NOT NULL,
    session_id integer NOT NULL,
    name text NOT NULL,
    faction text,
    rank text,
    personality_traits jsonb DEFAULT '[]'::jsonb,
    intel_value integer DEFAULT 1,
    resistance integer DEFAULT 50,
    status text DEFAULT 'captured'::text NOT NULL,
    cell_ship_id integer,
    cell_security text DEFAULT 'standard'::text,
    interrogations_count integer DEFAULT 0,
    last_interrogation_method text,
    secrets_jsonb jsonb DEFAULT '[]'::jsonb,
    intel_extracted jsonb DEFAULT '[]'::jsonb,
    intimacy_flag boolean DEFAULT false,
    intimacy_path text,
    escape_risk_pct integer DEFAULT 0,
    escape_attempts integer DEFAULT 0,
    captured_at timestamp with time zone DEFAULT now(),
    captured_from_ship text,
    captured_in_engagement integer,
    released_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    conversion_path text,
    conversion_progress integer DEFAULT 0,
    death_cause text,
    death_session integer,
    held_sessions integer DEFAULT 0,
    CONSTRAINT prisoners_cell_security_check CHECK ((cell_security = ANY (ARRAY['minimal'::text, 'standard'::text, 'maximum'::text, 'isolated'::text]))),
    CONSTRAINT prisoners_escape_risk_pct_check CHECK (((escape_risk_pct >= 0) AND (escape_risk_pct <= 100))),
    CONSTRAINT prisoners_intel_value_check CHECK (((intel_value >= 1) AND (intel_value <= 100))),
    CONSTRAINT prisoners_intimacy_path_check CHECK (((intimacy_path IS NULL) OR (intimacy_path = ANY (ARRAY['fear'::text, 'seduction'::text, 'stockholm'::text])))),
    CONSTRAINT prisoners_resistance_check CHECK (((resistance >= 0) AND (resistance <= 100))),
    CONSTRAINT prisoners_status_check CHECK ((status = ANY (ARRAY['captured'::text, 'holding'::text, 'interrogated'::text, 'broken'::text, 'recruited'::text, 'released'::text, 'exchanged'::text, 'executed'::text, 'escaped'::text, 'dead'::text, 'transferred'::text])))
);


--
-- Name: prisoners_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.prisoners_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prisoners_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.prisoners_id_seq OWNED BY maya_rp.prisoners.id;


--
-- Name: production_consumption_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.production_consumption_log (
    id integer NOT NULL,
    production_type character varying(50),
    production_name character varying(100),
    resource_id integer,
    quantity_used integer,
    consumed_at timestamp without time zone DEFAULT now()
);


--
-- Name: production_consumption_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.production_consumption_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: production_consumption_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.production_consumption_log_id_seq OWNED BY maya_rp.production_consumption_log.id;


--
-- Name: production_lines; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.production_lines (
    id integer NOT NULL,
    colony_id integer,
    name text,
    recipe_id integer,
    status text DEFAULT 'idle'::text,
    efficiency numeric DEFAULT 1.0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: production_lines_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.production_lines_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: production_lines_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.production_lines_id_seq OWNED BY maya_rp.production_lines.id;


--
-- Name: production_queue; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.production_queue (
    id integer NOT NULL,
    session_id integer,
    ship_name text NOT NULL,
    ship_type text NOT NULL,
    hull_class text DEFAULT 'capital'::text,
    status text DEFAULT 'planned'::text,
    priority integer DEFAULT 1,
    alloy_cost bigint DEFAULT 0,
    fuel_cost bigint DEFAULT 0,
    credit_cost bigint DEFAULT 0,
    build_time_hours integer DEFAULT 24,
    progress_pct integer DEFAULT 0,
    assigned_yard text DEFAULT 'Heaven'::text,
    notes text DEFAULT ''::text
);


--
-- Name: production_queue_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.production_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: production_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.production_queue_id_seq OWNED BY maya_rp.production_queue.id;


--
-- Name: production_requirements; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.production_requirements (
    id integer NOT NULL,
    production_type character varying(50) NOT NULL,
    production_name character varying(100) NOT NULL,
    resource_id integer,
    quantity_needed integer NOT NULL
);


--
-- Name: production_requirements_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.production_requirements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: production_requirements_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.production_requirements_id_seq OWNED BY maya_rp.production_requirements.id;


--
-- Name: propaganda_campaigns; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.propaganda_campaigns (
    id integer NOT NULL,
    session_id integer,
    faction_name character varying(100) NOT NULL,
    campaign_type character varying(50) NOT NULL,
    budget double precision DEFAULT 0,
    effectiveness double precision DEFAULT 0.5,
    duration_ticks integer DEFAULT 5,
    ticks_remaining integer DEFAULT 5,
    target_faction character varying(100),
    started_at timestamp with time zone DEFAULT now()
);


--
-- Name: propaganda_campaigns_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.propaganda_campaigns_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: propaganda_campaigns_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.propaganda_campaigns_id_seq OWNED BY maya_rp.propaganda_campaigns.id;


--
-- Name: public_opinion; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.public_opinion (
    id integer NOT NULL,
    session_id integer,
    faction_name character varying(100) NOT NULL,
    approval double precision DEFAULT 50.0,
    fear double precision DEFAULT 10.0,
    trust double precision DEFAULT 50.0,
    last_updated timestamp with time zone
);


--
-- Name: public_opinion_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.public_opinion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: public_opinion_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.public_opinion_id_seq OWNED BY maya_rp.public_opinion.id;


--
-- Name: quarterly_tasks; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.quarterly_tasks (
    id integer NOT NULL,
    session_id integer,
    quarter integer,
    task_index integer,
    title text,
    objective text,
    target_value integer DEFAULT 0,
    progress integer DEFAULT 0,
    reward_type text DEFAULT 'blueprint'::text,
    reward_value bigint DEFAULT 0,
    status text DEFAULT 'active'::text,
    created_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone,
    task_type text DEFAULT 'generic'::text,
    target text DEFAULT ''::text,
    required_amount integer DEFAULT 0,
    current_progress integer DEFAULT 0,
    reward_blueprint text DEFAULT ''::text
);


--
-- Name: quarterly_tasks_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.quarterly_tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: quarterly_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.quarterly_tasks_id_seq OWNED BY maya_rp.quarterly_tasks.id;


--
-- Name: quests; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.quests (
    id integer NOT NULL,
    session_id integer NOT NULL,
    title text NOT NULL,
    description text,
    quest_type text NOT NULL,
    giver text DEFAULT 'Fate'::text,
    reward_alloy bigint DEFAULT 0,
    reward_credit bigint DEFAULT 0,
    reward_item text,
    objectives jsonb DEFAULT '[]'::jsonb,
    status text DEFAULT 'available'::text NOT NULL,
    narrative_chain jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT quests_quest_type_check CHECK ((quest_type = ANY (ARRAY['combat'::text, 'exploration'::text, 'companion'::text, 'territory'::text, 'interrogation'::text, 'research'::text, 'trade'::text, 'diplomacy'::text, 'dark'::text, 'cosmic'::text]))),
    CONSTRAINT quests_status_check CHECK ((status = ANY (ARRAY['available'::text, 'accepted'::text, 'active'::text, 'completed'::text, 'failed'::text])))
);


--
-- Name: quests_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.quests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: quests_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.quests_id_seq OWNED BY maya_rp.quests.id;


--
-- Name: raid_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.raid_log (
    id integer NOT NULL,
    raider_faction_id integer,
    target_faction_id integer,
    supply_line_id integer,
    loot_amount integer,
    happened_at timestamp without time zone DEFAULT now()
);


--
-- Name: raid_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.raid_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: raid_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.raid_log_id_seq OWNED BY maya_rp.raid_log.id;


--
-- Name: recipes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.recipes (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    inputs jsonb DEFAULT '{}'::jsonb NOT NULL,
    outputs jsonb DEFAULT '{}'::jsonb NOT NULL,
    cycle_time_hours double precision DEFAULT 1.0,
    tech_requirement character varying(100)
);


--
-- Name: recipes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.recipes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recipes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.recipes_id_seq OWNED BY maya_rp.recipes.id;


--
-- Name: refill_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.refill_log (
    id integer NOT NULL,
    session_id integer,
    legion character varying,
    ship_type character varying,
    ship_name character varying,
    tier integer,
    crew integer,
    game_day integer,
    refilled boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: refill_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.refill_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: refill_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.refill_log_id_seq OWNED BY maya_rp.refill_log.id;


--
-- Name: reputation_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.reputation_events (
    id integer NOT NULL,
    faction_id integer,
    event_type character varying(50) NOT NULL,
    reputation_change integer NOT NULL,
    details text,
    happened_at timestamp without time zone DEFAULT now()
);


--
-- Name: reputation_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.reputation_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: reputation_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.reputation_events_id_seq OWNED BY maya_rp.reputation_events.id;


--
-- Name: research_labs; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.research_labs (
    id integer NOT NULL,
    colony_id integer,
    name text,
    level integer DEFAULT 1,
    research_field text,
    research_rate numeric DEFAULT 5.0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: research_labs_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.research_labs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: research_labs_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.research_labs_id_seq OWNED BY maya_rp.research_labs.id;


--
-- Name: research_projects; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.research_projects (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    field character varying(50),
    cost_credits integer NOT NULL,
    cost_research_points integer NOT NULL,
    duration_days integer NOT NULL,
    unlocked boolean DEFAULT false,
    progress_pct numeric DEFAULT 0,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    prerequisite_id integer,
    effect_type character varying(50),
    effect_value numeric,
    resource_costs jsonb,
    tech_tree_path jsonb,
    bonus_type character varying(50),
    bonus_value numeric,
    category character varying(50),
    unlock_text text,
    blueprint_price bigint DEFAULT 0,
    saleable boolean DEFAULT false
);


--
-- Name: research_projects_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.research_projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: research_projects_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.research_projects_id_seq OWNED BY maya_rp.research_projects.id;


--
-- Name: research_queue; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.research_queue (
    id integer NOT NULL,
    project_id integer,
    session_id integer DEFAULT 3,
    queue_position integer,
    status character varying(20) DEFAULT 'pending'::character varying
);


--
-- Name: research_queue_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.research_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: research_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.research_queue_id_seq OWNED BY maya_rp.research_queue.id;


--
-- Name: resource_inventory; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.resource_inventory (
    resource_id integer NOT NULL,
    quantity bigint DEFAULT 0 NOT NULL,
    last_updated timestamp without time zone DEFAULT now()
);


--
-- Name: strategic_resources; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.strategic_resources (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    rarity character varying(20) DEFAULT 'common'::character varying,
    base_value numeric DEFAULT 100,
    renewable boolean DEFAULT false,
    extraction_rate_base numeric DEFAULT 1,
    description text,
    requires_tech text,
    unlocks jsonb
);


--
-- Name: territory_resources; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.territory_resources (
    id integer NOT NULL,
    territory_id integer,
    resource_id integer,
    deposit_size bigint NOT NULL,
    current_extracted bigint DEFAULT 0,
    extraction_rate numeric DEFAULT 1,
    last_extracted timestamp without time zone,
    discovered boolean DEFAULT true,
    extraction_modifier numeric DEFAULT 1.0,
    CONSTRAINT positive_remaining CHECK ((current_extracted <= deposit_size))
);


--
-- Name: resource_overview; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.resource_overview AS
 SELECT t.system_name AS territory,
    sr.name AS resource,
    sr.category,
    sr.rarity,
    tr.deposit_size,
    tr.current_extracted,
    (tr.deposit_size - tr.current_extracted) AS remaining,
    tr.extraction_rate,
    (((tr.extraction_rate * sr.base_value) * 0.8))::bigint AS estimated_daily_credits
   FROM ((maya_rp.territory_resources tr
     JOIN maya_rp.territory t ON ((t.id = tr.territory_id)))
     JOIN maya_rp.strategic_resources sr ON ((sr.id = tr.resource_id)))
  WHERE (tr.current_extracted < tr.deposit_size)
  ORDER BY t.system_name, sr.rarity DESC;


--
-- Name: resource_production; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.resource_production (
    source text NOT NULL,
    resource_type text NOT NULL,
    amount_per_day integer NOT NULL,
    description text,
    resource_id integer
);


--
-- Name: resources; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.resources (
    session_id integer DEFAULT 1 NOT NULL,
    alloys bigint DEFAULT 0,
    fuel bigint DEFAULT 0,
    credits bigint DEFAULT 0,
    population bigint DEFAULT 0,
    tech_score integer DEFAULT 0,
    current_tier integer DEFAULT 1,
    influence integer DEFAULT 0,
    dream_essence integer DEFAULT 0,
    last_tick_at timestamp with time zone DEFAULT now(),
    fear integer DEFAULT 0,
    daemon_tick_at timestamp with time zone DEFAULT now(),
    rare_earth integer DEFAULT 0,
    starsteel integer DEFAULT 0,
    void_crystal integer DEFAULT 0,
    aetherium integer DEFAULT 0,
    aggregate_morale integer DEFAULT 50,
    crew_pool bigint DEFAULT 0,
    crew_trained_total bigint DEFAULT 0,
    crew_consumed_total bigint DEFAULT 0
);


--
-- Name: roll_history; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.roll_history (
    id bigint NOT NULL,
    session_id integer NOT NULL,
    roll_type_id integer,
    roll_code text NOT NULL,
    source_table text NOT NULL,
    source_id integer NOT NULL,
    source_name text,
    dice_used text NOT NULL,
    raw_roll integer NOT NULL,
    modifier_total integer DEFAULT 0 NOT NULL,
    final_score integer NOT NULL,
    difficulty_id integer,
    dc integer NOT NULL,
    outcome text NOT NULL,
    narrative text,
    modifiers_breakdown jsonb,
    delta_applied jsonb,
    triggered_by text DEFAULT 'ai_narrator'::text NOT NULL,
    context_event_id bigint,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: roll_history_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.roll_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roll_history_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.roll_history_id_seq OWNED BY maya_rp.roll_history.id;


--
-- Name: roll_outcome_tiers; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.roll_outcome_tiers (
    id integer NOT NULL,
    outcome text NOT NULL,
    threshold_label text NOT NULL,
    narrative_tag text NOT NULL,
    color text
);


--
-- Name: roll_outcome_tiers_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.roll_outcome_tiers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roll_outcome_tiers_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.roll_outcome_tiers_id_seq OWNED BY maya_rp.roll_outcome_tiers.id;


--
-- Name: roll_state; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.roll_state (
    session_id integer NOT NULL,
    last_rolled_game_day integer,
    build_progress jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: roll_types; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.roll_types (
    id integer NOT NULL,
    roll_code text NOT NULL,
    domain text NOT NULL,
    description text,
    base_dice text DEFAULT '1d20'::text NOT NULL,
    source_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    target_table text,
    target_column text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: roll_types_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.roll_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roll_types_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.roll_types_id_seq OWNED BY maya_rp.roll_types.id;


--
-- Name: romance_arcs; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.romance_arcs (
    id integer NOT NULL,
    session_id integer NOT NULL,
    character_id integer NOT NULL,
    arc_stage text DEFAULT 'strangers'::text NOT NULL,
    intimacy_level integer DEFAULT 0 NOT NULL,
    first_kiss_session integer,
    first_intimacy_session integer,
    active_scene text,
    scene_log jsonb DEFAULT '[]'::jsonb NOT NULL,
    pursuit_stage text DEFAULT 'you_chase'::text,
    saturation_pct integer DEFAULT 0,
    last_intimacy_session integer,
    initiatives_by_companion integer DEFAULT 0,
    initiatives_by_player integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    nights_shared integer DEFAULT 0,
    CONSTRAINT romance_arcs_arc_stage_check CHECK ((arc_stage = ANY (ARRAY['strangers'::text, 'acquaintance'::text, 'attraction'::text, 'deepening'::text, 'intimacy'::text, 'devotion'::text, 'flirtation'::text, 'kiss'::text, 'estrangement'::text]))),
    CONSTRAINT romance_arcs_intimacy_level_check CHECK (((intimacy_level >= 0) AND (intimacy_level <= 10))),
    CONSTRAINT romance_arcs_pursuit_stage_check CHECK ((pursuit_stage = ANY (ARRAY['you_chase'::text, 'mutual'::text, 'they_chase'::text, 'they_consume'::text]))),
    CONSTRAINT romance_arcs_saturation_pct_check CHECK (((saturation_pct >= 0) AND (saturation_pct <= 100)))
);


--
-- Name: romance_arcs_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.romance_arcs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: romance_arcs_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.romance_arcs_id_seq OWNED BY maya_rp.romance_arcs.id;


--
-- Name: romance_tiers; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.romance_tiers (
    id integer NOT NULL,
    tier_name text NOT NULL,
    bond_threshold integer NOT NULL,
    unlocked_actions jsonb DEFAULT '[]'::jsonb NOT NULL,
    sensory_level text DEFAULT 'moderate'::text NOT NULL,
    prose_density text DEFAULT 'standard'::text NOT NULL
);


--
-- Name: romance_tiers_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.romance_tiers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: romance_tiers_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.romance_tiers_id_seq OWNED BY maya_rp.romance_tiers.id;


--
-- Name: royal_accounts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.royal_accounts (
    id integer NOT NULL,
    session_id integer NOT NULL,
    account_name text NOT NULL,
    account_type text NOT NULL,
    balance_credits bigint DEFAULT 0,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT royal_accounts_account_type_check CHECK ((account_type = ANY (ARRAY['king_personal'::text, 'queen_shared'::text, 'house_fund'::text, 'foundation'::text])))
);


--
-- Name: royal_accounts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.royal_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: royal_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.royal_accounts_id_seq OWNED BY maya_rp.royal_accounts.id;


--
-- Name: royal_offspring; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.royal_offspring (
    id integer NOT NULL,
    session_id integer DEFAULT 3,
    mother_name text NOT NULL,
    father_name text DEFAULT 'King Izzat al-Setia'::text,
    conceived_at timestamp without time zone DEFAULT now(),
    due_date timestamp without time zone,
    delivery_date timestamp without time zone,
    status text DEFAULT 'pregnant'::text,
    child_name text,
    gender text,
    notes text
);


--
-- Name: royal_offspring_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.royal_offspring_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: royal_offspring_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.royal_offspring_id_seq OWNED BY maya_rp.royal_offspring.id;


--
-- Name: savepoints; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.savepoints (
    id integer NOT NULL,
    session_id integer,
    label character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    snapshot jsonb
);


--
-- Name: savepoints_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.savepoints_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: savepoints_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.savepoints_id_seq OWNED BY maya_rp.savepoints.id;


--
-- Name: scene_stack; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.scene_stack (
    id integer NOT NULL,
    session_id integer,
    interrupt_type character varying(30),
    context_jsonb jsonb NOT NULL,
    pushed_at_game_day integer,
    status character varying(20) DEFAULT 'suspended'::character varying,
    resolved_at_game_day integer
);


--
-- Name: scene_stack_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.scene_stack_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scene_stack_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.scene_stack_id_seq OWNED BY maya_rp.scene_stack.id;


--
-- Name: science_missions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.science_missions (
    id integer NOT NULL,
    session_id integer,
    ship_id integer,
    sector_id integer,
    mission_type character varying(50),
    status character varying(20) DEFAULT 'active'::character varying,
    progress integer DEFAULT 0,
    target_progress integer DEFAULT 100,
    scientist_id integer,
    research_reward integer DEFAULT 50,
    started_at timestamp with time zone DEFAULT now()
);


--
-- Name: science_missions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.science_missions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: science_missions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.science_missions_id_seq OWNED BY maya_rp.science_missions.id;


--
-- Name: scientific_theories; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.scientific_theories (
    id integer NOT NULL,
    session_id integer,
    name character varying(200) NOT NULL,
    field character varying(50),
    tier integer DEFAULT 1,
    hypothesis text,
    evidence integer DEFAULT 0,
    evidence_needed integer DEFAULT 100,
    confirmed boolean DEFAULT false,
    unlocks jsonb DEFAULT '{}'::jsonb
);


--
-- Name: scientific_theories_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.scientific_theories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scientific_theories_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.scientific_theories_id_seq OWNED BY maya_rp.scientific_theories.id;


--
-- Name: scientist_assignments; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.scientist_assignments (
    id integer NOT NULL,
    character_id integer,
    lab_id integer,
    specialty text,
    bonus numeric DEFAULT 0.25
);


--
-- Name: scientist_assignments_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.scientist_assignments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scientist_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.scientist_assignments_id_seq OWNED BY maya_rp.scientist_assignments.id;


--
-- Name: score_history; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.score_history (
    id integer NOT NULL,
    faction_id integer,
    turn integer,
    score integer,
    recorded_at timestamp without time zone DEFAULT now()
);


--
-- Name: score_history_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.score_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: score_history_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.score_history_id_seq OWNED BY maya_rp.score_history.id;


--
-- Name: secrets; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.secrets (
    id integer NOT NULL,
    session_id integer,
    secret_type character varying(30),
    holder_character_id integer,
    content text NOT NULL,
    hidden_from_ids integer[],
    discovery_trigger text,
    consequence_description text,
    planted_game_day integer,
    auto_reveal_game_day integer,
    revealed_game_day integer,
    revelation_context text,
    status character varying(20) DEFAULT 'active'::character varying
);


--
-- Name: secrets_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.secrets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: secrets_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.secrets_id_seq OWNED BY maya_rp.secrets.id;


--
-- Name: sector_connections; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.sector_connections (
    id integer NOT NULL,
    session_id integer,
    from_sector_id integer,
    to_sector_id integer,
    distance double precision DEFAULT 1.0,
    travel_time_hours double precision DEFAULT 24.0,
    lane_type character varying(50) DEFAULT 'standard'::character varying
);


--
-- Name: sector_connections_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.sector_connections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_connections_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.sector_connections_id_seq OWNED BY maya_rp.sector_connections.id;


--
-- Name: sector_resources; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.sector_resources (
    id integer NOT NULL,
    sector_id integer,
    resource_type character varying(50) NOT NULL,
    abundance double precision DEFAULT 1.0,
    depletion_rate double precision DEFAULT 0.0
);


--
-- Name: sector_resources_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.sector_resources_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_resources_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.sector_resources_id_seq OWNED BY maya_rp.sector_resources.id;


--
-- Name: sector_visibility; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.sector_visibility (
    id integer NOT NULL,
    session_id integer,
    sector_id integer,
    visibility_level character varying(20) DEFAULT 'unexplored'::character varying,
    last_scouted_at timestamp with time zone
);


--
-- Name: sector_visibility_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.sector_visibility_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_visibility_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.sector_visibility_id_seq OWNED BY maya_rp.sector_visibility.id;


--
-- Name: sectors_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.sectors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sectors_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.sectors_id_seq OWNED BY maya_rp.sectors.id;


--
-- Name: sessions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.sessions (
    id integer NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    summary text,
    created_at timestamp with time zone DEFAULT now(),
    telegram_chat_id bigint,
    primary_partner_id integer,
    seed bigint,
    seed_version integer DEFAULT 1,
    save_label character varying(100),
    game_day integer DEFAULT 1,
    king_present boolean DEFAULT true,
    dark_mode boolean DEFAULT false
);


--
-- Name: sessions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.sessions_id_seq OWNED BY maya_rp.sessions.id;


--
-- Name: ship_armaments; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ship_armaments (
    id integer NOT NULL,
    ship_id integer NOT NULL,
    weapon_id integer NOT NULL,
    slot_index integer NOT NULL,
    slot_size text NOT NULL,
    installed_at timestamp with time zone DEFAULT now()
);


--
-- Name: ship_armaments_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ship_armaments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ship_armaments_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ship_armaments_id_seq OWNED BY maya_rp.ship_armaments.id;


--
-- Name: ship_classes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ship_classes (
    id integer NOT NULL,
    class_name text NOT NULL,
    category text NOT NULL,
    base_mass integer NOT NULL,
    base_length integer NOT NULL,
    base_crew integer NOT NULL,
    base_hull integer NOT NULL,
    base_speed integer NOT NULL,
    module_slots integer DEFAULT 0 NOT NULL,
    weapon_slots text NOT NULL,
    scale_factor double precision DEFAULT 1.15 NOT NULL,
    special_rules jsonb DEFAULT '{}'::jsonb
);


--
-- Name: ship_classes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ship_classes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ship_classes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ship_classes_id_seq OWNED BY maya_rp.ship_classes.id;


--
-- Name: ship_modules; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ship_modules (
    id integer NOT NULL,
    ship_id integer NOT NULL,
    module_id integer NOT NULL,
    slot_index integer NOT NULL,
    installed_at timestamp with time zone DEFAULT now()
);


--
-- Name: ship_modules_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ship_modules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ship_modules_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ship_modules_id_seq OWNED BY maya_rp.ship_modules.id;


--
-- Name: ship_roles; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ship_roles (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    description text,
    base_stats jsonb,
    required_tech character varying(50),
    tactics_allowed jsonb
);


--
-- Name: ship_roles_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ship_roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ship_roles_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ship_roles_id_seq OWNED BY maya_rp.ship_roles.id;


--
-- Name: ship_sub_classes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ship_sub_classes (
    id integer NOT NULL,
    ship_type text NOT NULL,
    sub_class text NOT NULL,
    hull_mult numeric(5,2) DEFAULT 1.00 NOT NULL,
    speed_mult numeric(5,2) DEFAULT 1.00 NOT NULL,
    crew_mult numeric(5,2) DEFAULT 1.00 NOT NULL,
    power_mult numeric(5,2) DEFAULT 1.00 NOT NULL,
    description text
);


--
-- Name: ship_sub_classes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ship_sub_classes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ship_sub_classes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ship_sub_classes_id_seq OWNED BY maya_rp.ship_sub_classes.id;


--
-- Name: ship_tech_bonuses; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ship_tech_bonuses (
    id integer NOT NULL,
    ship_type character varying(50) NOT NULL,
    bonus_type character varying(50) NOT NULL,
    value numeric NOT NULL,
    source_research_id integer,
    applied_at timestamp without time zone DEFAULT now()
);


--
-- Name: ship_tech_bonuses_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ship_tech_bonuses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ship_tech_bonuses_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ship_tech_bonuses_id_seq OWNED BY maya_rp.ship_tech_bonuses.id;


--
-- Name: ship_types; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ship_types (
    code text NOT NULL,
    name text NOT NULL,
    description text,
    buildable boolean DEFAULT false NOT NULL,
    special_rules jsonb DEFAULT '{}'::jsonb,
    visual_clue text
);


--
-- Name: ships; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.ships (
    id integer NOT NULL,
    session_id integer DEFAULT 1 NOT NULL,
    name text NOT NULL,
    class_id integer DEFAULT 1,
    ship_type text DEFAULT 'frigate'::text NOT NULL,
    mass integer DEFAULT 1000,
    length_m integer DEFAULT 100,
    hull integer DEFAULT 100,
    hull_current integer DEFAULT 100,
    speed integer DEFAULT 10,
    crew integer DEFAULT 10,
    fighter_capacity integer DEFAULT 0,
    location text DEFAULT 'Silent Forge'::text,
    status text DEFAULT 'active'::text NOT NULL,
    tier integer DEFAULT 1,
    veteran_kills integer DEFAULT 0,
    rank text,
    experience integer DEFAULT 0,
    cell_capacity integer DEFAULT 0,
    security_tier integer DEFAULT 0,
    is_colony_ship boolean DEFAULT false,
    colonists integer DEFAULT 0,
    weapon_slots integer DEFAULT 3,
    shield_generators integer DEFAULT 1,
    engine_type character varying(50) DEFAULT 'standard'::character varying,
    combat_modules jsonb DEFAULT '[]'::jsonb,
    role character varying(50) DEFAULT 'line'::character varying,
    power_rating integer DEFAULT 0,
    sub_class text,
    battle_honors integer DEFAULT 0,
    legacy_score integer DEFAULT 0,
    crew_current integer DEFAULT 0,
    crew_required integer DEFAULT 0,
    undercrewed_penalty numeric DEFAULT 0.0,
    scars_jsonb jsonb DEFAULT '[]'::jsonb,
    ship_rank text DEFAULT 'Standard'::text,
    min_clearance integer DEFAULT 1,
    territory_id integer,
    faction_id integer,
    CONSTRAINT ships_security_tier_check CHECK (((security_tier >= 0) AND (security_tier <= 5)))
);


--
-- Name: ships_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.ships_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ships_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.ships_id_seq OWNED BY maya_rp.ships.id;


--
-- Name: sieges; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.sieges (
    id integer NOT NULL,
    session_id integer NOT NULL,
    territory_id integer,
    target_system text NOT NULL,
    target_faction text NOT NULL,
    attacker_power integer DEFAULT 0 NOT NULL,
    defender_power integer DEFAULT 0 NOT NULL,
    phase integer DEFAULT 1 NOT NULL,
    max_phases integer DEFAULT 5 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    damage_dealt integer DEFAULT 0,
    casualties_taken integer DEFAULT 0,
    morale_impact integer DEFAULT 0,
    started_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    target_territory_id integer,
    CONSTRAINT sieges_phase_check CHECK (((phase >= 1) AND (phase <= 5))),
    CONSTRAINT sieges_status_check CHECK ((status = ANY (ARRAY['active'::text, 'victory'::text, 'routed'::text, 'stalemate'::text, 'abandoned'::text])))
);


--
-- Name: sieges_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.sieges_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sieges_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.sieges_id_seq OWNED BY maya_rp.sieges.id;


--
-- Name: slave_births; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.slave_births (
    id integer NOT NULL,
    parent_slave_id integer,
    child_name character varying(100),
    born_at timestamp without time zone DEFAULT now(),
    inherited_traits jsonb
);


--
-- Name: slave_births_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.slave_births_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: slave_births_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.slave_births_id_seq OWNED BY maya_rp.slave_births.id;


--
-- Name: slave_market; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.slave_market (
    id integer NOT NULL,
    session_id integer DEFAULT 3,
    territory_id integer,
    slave_name character varying(100),
    species character varying(50),
    gender character varying(10),
    age integer,
    strength integer,
    intelligence integer,
    price integer,
    availability boolean DEFAULT true,
    price_tier text DEFAULT 'common'::text,
    category text DEFAULT 'common'::text,
    hidden_talent text,
    functional_role text DEFAULT 'worker'::text,
    clearance_level integer DEFAULT 1
);


--
-- Name: slave_market_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.slave_market_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: slave_market_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.slave_market_id_seq OWNED BY maya_rp.slave_market.id;


--
-- Name: slaves; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.slaves (
    id integer NOT NULL,
    session_id integer DEFAULT 3,
    name character varying(100),
    species character varying(50),
    gender character varying(10),
    age integer DEFAULT 20,
    strength integer DEFAULT 5,
    intelligence integer DEFAULT 5,
    loyalty integer DEFAULT 20,
    health integer DEFAULT 80,
    assigned_to character varying(50),
    assigned_id integer,
    role character varying(50) DEFAULT 'laborer'::character varying,
    acquired_at timestamp without time zone DEFAULT now(),
    acquired_from character varying(50),
    cost integer DEFAULT 1000,
    status character varying(20) DEFAULT 'active'::character varying,
    last_activity timestamp without time zone
);


--
-- Name: slave_overview; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.slave_overview AS
 SELECT s.id,
    s.name,
    s.species,
    s.role,
    s.assigned_to,
    s.loyalty,
    s.health,
    s.status,
    t.system_name AS territory_name,
    s.acquired_from,
    s.acquired_at
   FROM (maya_rp.slaves s
     LEFT JOIN maya_rp.territory t ON (((t.id = s.assigned_id) AND ((s.assigned_to)::text = 'territory'::text))))
  WHERE ((s.status)::text <> ALL ((ARRAY['dead'::character varying, 'escaped'::character varying])::text[]))
  ORDER BY s.loyalty, s.health DESC;


--
-- Name: slave_revolts; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.slave_revolts (
    id integer NOT NULL,
    session_id integer DEFAULT 3,
    territory_id integer,
    start_time timestamp without time zone DEFAULT now(),
    end_time timestamp without time zone,
    size integer DEFAULT 0,
    severity integer DEFAULT 1,
    outcome character varying(20),
    casualties integer DEFAULT 0,
    narrative text
);


--
-- Name: slave_revolts_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.slave_revolts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: slave_revolts_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.slave_revolts_id_seq OWNED BY maya_rp.slave_revolts.id;


--
-- Name: slave_training; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.slave_training (
    id integer NOT NULL,
    slave_id integer,
    training_type character varying(50),
    progress integer DEFAULT 0,
    started_at timestamp without time zone DEFAULT now(),
    completed_at timestamp without time zone,
    trainer_id integer
);


--
-- Name: slave_training_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.slave_training_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: slave_training_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.slave_training_id_seq OWNED BY maya_rp.slave_training.id;


--
-- Name: slaves_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.slaves_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: slaves_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.slaves_id_seq OWNED BY maya_rp.slaves.id;


--
-- Name: social_events; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.social_events (
    id integer NOT NULL,
    session_id integer NOT NULL,
    event_type text NOT NULL,
    title text NOT NULL,
    location_id integer,
    participants jsonb DEFAULT '[]'::jsonb NOT NULL,
    tension_before integer DEFAULT 50,
    tension_delta integer DEFAULT 0,
    outcome text,
    morale_after integer,
    loyalty_shifts jsonb DEFAULT '[]'::jsonb,
    dialogue_log jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    diplomatic_action_id integer,
    CONSTRAINT social_events_event_type_check CHECK ((event_type = ANY (ARRAY['banquet'::text, 'ceremony'::text, 'argument'::text, 'funeral'::text, 'rally'::text, 'confrontation'::text, 'reconciliation'::text, 'celebration'::text, 'mentorship'::text, 'gossip'::text, 'confession'::text, 'trial'::text])))
);


--
-- Name: social_events_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.social_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: social_events_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.social_events_id_seq OWNED BY maya_rp.social_events.id;


--
-- Name: social_templates; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.social_templates (
    id integer NOT NULL,
    event_type text NOT NULL,
    name text NOT NULL,
    min_participants integer DEFAULT 2,
    mood_tags jsonb DEFAULT '[]'::jsonb,
    typical_duration text DEFAULT '1 scene'::text,
    possible_outcomes jsonb DEFAULT '[]'::jsonb
);


--
-- Name: social_templates_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.social_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: social_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.social_templates_id_seq OWNED BY maya_rp.social_templates.id;


--
-- Name: space_animals; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.space_animals (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    species character varying(100) NOT NULL,
    description text,
    habitat character varying(50),
    aggression integer DEFAULT 5,
    taming_difficulty integer DEFAULT 5,
    resource_value jsonb DEFAULT '{"credits": 100}'::jsonb,
    special_ability text,
    rarity character varying(20) DEFAULT 'common'::character varying
);


--
-- Name: space_animals_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.space_animals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: space_animals_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.space_animals_id_seq OWNED BY maya_rp.space_animals.id;


--
-- Name: space_anomalies; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.space_anomalies (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    type character varying(50) NOT NULL,
    description text,
    discovery_trigger character varying(50),
    reward_pool jsonb DEFAULT '{"credits": 500}'::jsonb,
    danger_level integer DEFAULT 1,
    effects jsonb,
    active boolean DEFAULT true,
    rarity character varying(20) DEFAULT 'common'::character varying
);


--
-- Name: space_anomalies_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.space_anomalies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: space_anomalies_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.space_anomalies_id_seq OWNED BY maya_rp.space_anomalies.id;


--
-- Name: space_lanes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.space_lanes (
    id integer NOT NULL,
    session_id integer NOT NULL,
    origin text NOT NULL,
    destination text NOT NULL,
    lane_type text DEFAULT 'trade'::text,
    threat_level integer DEFAULT 0,
    intel_level integer DEFAULT 0,
    last_scouted timestamp with time zone
);


--
-- Name: space_lanes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.space_lanes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: space_lanes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.space_lanes_id_seq OWNED BY maya_rp.space_lanes.id;


--
-- Name: species_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.species_catalog (
    id integer NOT NULL,
    name text NOT NULL,
    category text DEFAULT 'organic'::text,
    base_strength integer DEFAULT 5,
    base_intelligence integer DEFAULT 5,
    base_charisma integer DEFAULT 5,
    lifespan_years integer DEFAULT 80,
    crew_role_bonus text DEFAULT ''::text,
    clearance_default integer DEFAULT 1,
    market_available boolean DEFAULT true,
    traits_common jsonb DEFAULT '[]'::jsonb,
    notes text DEFAULT ''::text,
    has_breasts boolean DEFAULT false,
    soft_body boolean DEFAULT false,
    can_transform_human boolean DEFAULT false,
    has_buttocks boolean DEFAULT false,
    compatible_anatomy boolean DEFAULT false,
    romance_compatible boolean DEFAULT false,
    compat_notes text DEFAULT ''::text,
    human_like_pct integer DEFAULT 0
);


--
-- Name: species_catalog_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.species_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: species_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.species_catalog_id_seq OWNED BY maya_rp.species_catalog.id;


--
-- Name: spy_networks; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.spy_networks (
    id integer NOT NULL,
    faction_id integer,
    target_faction_id integer,
    established_at timestamp without time zone DEFAULT now(),
    active boolean DEFAULT true,
    agents integer DEFAULT 1,
    effectiveness numeric DEFAULT 0.1,
    last_operation timestamp without time zone,
    notes text
);


--
-- Name: spy_networks_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.spy_networks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: spy_networks_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.spy_networks_id_seq OWNED BY maya_rp.spy_networks.id;


--
-- Name: standing_orders; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.standing_orders (
    id integer NOT NULL,
    session_id integer NOT NULL,
    order_name text NOT NULL,
    detail text NOT NULL,
    rotation_hours integer DEFAULT 24 NOT NULL,
    current_unit text NOT NULL,
    next_rotation_at timestamp with time zone,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: standing_orders_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.standing_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: standing_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.standing_orders_id_seq OWNED BY maya_rp.standing_orders.id;


--
-- Name: state; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.state (
    session_id integer NOT NULL,
    variables jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: state_snapshots; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.state_snapshots (
    id integer NOT NULL,
    session_id integer NOT NULL,
    label text NOT NULL,
    state jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: state_snapshots_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.state_snapshots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: state_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.state_snapshots_id_seq OWNED BY maya_rp.state_snapshots.id;


--
-- Name: stealth_unit_types; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.stealth_unit_types (
    id integer NOT NULL,
    name text NOT NULL,
    cloak_level integer DEFAULT 50,
    speed text DEFAULT 'medium'::text,
    base_cost_alloys bigint DEFAULT 2000,
    max_lanes integer DEFAULT 1,
    abilities jsonb DEFAULT '[]'::jsonb,
    description text,
    CONSTRAINT stealth_unit_types_cloak_level_check CHECK (((cloak_level >= 0) AND (cloak_level <= 100)))
);


--
-- Name: stealth_unit_types_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.stealth_unit_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stealth_unit_types_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.stealth_unit_types_id_seq OWNED BY maya_rp.stealth_unit_types.id;


--
-- Name: stealth_units; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.stealth_units (
    id integer NOT NULL,
    session_id integer NOT NULL,
    unit_type_id integer NOT NULL,
    name text NOT NULL,
    assigned_lane text,
    status text DEFAULT 'active'::text,
    cloak_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: stealth_units_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.stealth_units_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stealth_units_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.stealth_units_id_seq OWNED BY maya_rp.stealth_units.id;


--
-- Name: stock_prices; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.stock_prices (
    resource_id integer NOT NULL,
    price numeric NOT NULL,
    last_updated timestamp without time zone DEFAULT now(),
    volatility numeric DEFAULT 0.05
);


--
-- Name: story_arcs; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.story_arcs (
    id integer NOT NULL,
    session_id integer,
    title character varying(100),
    theme character varying(30),
    central_conflict text,
    stakes_description text,
    phase character varying(30) DEFAULT 'setup'::character varying,
    sessions_in_phase integer DEFAULT 0,
    total_sessions integer DEFAULT 0,
    status character varying(20) DEFAULT 'active'::character varying,
    started_at timestamp with time zone DEFAULT now(),
    ended_at timestamp with time zone,
    collapse_type character varying(50) DEFAULT NULL::character varying,
    collapse_recovery text
);


--
-- Name: story_arcs_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.story_arcs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: story_arcs_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.story_arcs_id_seq OWNED BY maya_rp.story_arcs.id;


--
-- Name: story_checkpoints; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.story_checkpoints (
    id integer NOT NULL,
    session_id integer,
    checkpoint_number integer NOT NULL,
    label character varying(100),
    created_at timestamp without time zone DEFAULT now(),
    md_file_path character varying(255),
    metadata jsonb,
    active boolean DEFAULT false,
    CONSTRAINT chk_checkpoint_num CHECK (((checkpoint_number >= 1) AND (checkpoint_number <= 3)))
);


--
-- Name: story_checkpoints_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.story_checkpoints_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: story_checkpoints_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.story_checkpoints_id_seq OWNED BY maya_rp.story_checkpoints.id;


--
-- Name: story_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.story_log (
    id integer NOT NULL,
    session_id integer,
    happened_at timestamp without time zone DEFAULT now(),
    category character varying(50),
    title character varying(200),
    content text,
    tags jsonb,
    source_type character varying(50),
    source_id integer,
    importance integer DEFAULT 1
);


--
-- Name: story_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.story_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: story_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.story_log_id_seq OWNED BY maya_rp.story_log.id;


--
-- Name: strategic_resources_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.strategic_resources_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: strategic_resources_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.strategic_resources_id_seq OWNED BY maya_rp.strategic_resources.id;


--
-- Name: stream_templates; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.stream_templates (
    id integer NOT NULL,
    trigger_tag text NOT NULL,
    expanded_text text NOT NULL,
    category character varying(50) DEFAULT 'environment'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    trigger_tag_embed public.vector(768),
    readable_hint text,
    required_context jsonb DEFAULT '[]'::jsonb
);


--
-- Name: stream_templates_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.stream_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stream_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.stream_templates_id_seq OWNED BY maya_rp.stream_templates.id;


--
-- Name: supply_depots; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.supply_depots (
    id integer NOT NULL,
    territory_id integer,
    name character varying(100),
    capacity integer DEFAULT 1000,
    current_supply integer DEFAULT 0,
    resupply_rate integer DEFAULT 100
);


--
-- Name: supply_depots_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.supply_depots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: supply_depots_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.supply_depots_id_seq OWNED BY maya_rp.supply_depots.id;


--
-- Name: supply_lines; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.supply_lines (
    id integer NOT NULL,
    campaign_id integer,
    depot_id integer,
    active boolean DEFAULT true,
    last_supply timestamp without time zone
);


--
-- Name: supply_lines_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.supply_lines_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: supply_lines_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.supply_lines_id_seq OWNED BY maya_rp.supply_lines.id;


--
-- Name: tactical_states; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.tactical_states (
    id integer NOT NULL,
    session_id integer NOT NULL,
    engagement_id integer NOT NULL,
    tactic text NOT NULL,
    advantage jsonb DEFAULT '[]'::jsonb,
    disadvantage jsonb DEFAULT '[]'::jsonb,
    enemy_counter text,
    environment text DEFAULT 'open_space'::text NOT NULL,
    initiator text DEFAULT 'player'::text NOT NULL,
    companion_assist text,
    outcome text,
    next_beat text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT tactical_states_initiator_check CHECK ((initiator = ANY (ARRAY['player'::text, 'enemy'::text])))
);


--
-- Name: tactical_states_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.tactical_states_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tactical_states_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.tactical_states_id_seq OWNED BY maya_rp.tactical_states.id;


--
-- Name: tactics_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.tactics_catalog (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    category character varying(20) NOT NULL,
    description text,
    effect_multiplier numeric DEFAULT 1.0,
    condition jsonb
);


--
-- Name: tactics_catalog_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.tactics_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tactics_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.tactics_catalog_id_seq OWNED BY maya_rp.tactics_catalog.id;


--
-- Name: talent_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.talent_catalog (
    id integer NOT NULL,
    name text NOT NULL,
    category text NOT NULL,
    tier integer DEFAULT 1 NOT NULL,
    effect_type text NOT NULL,
    effect_value double precision DEFAULT 1.0 NOT NULL,
    description text,
    CONSTRAINT talent_catalog_category_check CHECK ((category = ANY (ARRAY['combat'::text, 'engineering'::text, 'logistics'::text, 'diplomacy'::text, 'covert'::text, 'command'::text, 'medical'::text, 'navigation'::text]))),
    CONSTRAINT talent_catalog_tier_check CHECK (((tier >= 1) AND (tier <= 5)))
);


--
-- Name: talent_catalog_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.talent_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: talent_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.talent_catalog_id_seq OWNED BY maya_rp.talent_catalog.id;


--
-- Name: task_routes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.task_routes (
    id integer NOT NULL,
    session_id integer NOT NULL,
    decree_id integer,
    from_seat integer,
    to_seat integer,
    task text NOT NULL,
    status text DEFAULT 'assigned'::text,
    response text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT task_routes_status_check CHECK ((status = ANY (ARRAY['assigned'::text, 'acknowledged'::text, 'in_progress'::text, 'completed'::text, 'rejected'::text])))
);


--
-- Name: task_routes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.task_routes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_routes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.task_routes_id_seq OWNED BY maya_rp.task_routes.id;


--
-- Name: tax_history; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.tax_history (
    id integer NOT NULL,
    territory_id integer,
    tax_rate numeric NOT NULL,
    population bigint NOT NULL,
    revenue_generated bigint NOT NULL,
    morale_impact integer DEFAULT 0,
    recorded_at timestamp without time zone DEFAULT now()
);


--
-- Name: tax_history_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.tax_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tax_history_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.tax_history_id_seq OWNED BY maya_rp.tax_history.id;


--
-- Name: tech_tree; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.tech_tree AS
 SELECT id,
    name,
    description,
    field,
    category,
    cost_credits,
    cost_research_points,
    duration_days,
    resource_costs,
    bonus_type,
    bonus_value,
    unlocked,
    progress_pct,
    tech_tree_path,
    ( SELECT COALESCE(array_agg(prereq.name), '{}'::character varying[]) AS "coalesce"
           FROM maya_rp.research_projects prereq
          WHERE ((prereq.name)::text IN ( SELECT jsonb_array_elements_text(rp.tech_tree_path) AS jsonb_array_elements_text))) AS prerequisites_names
   FROM maya_rp.research_projects rp
  ORDER BY field, category, id;


--
-- Name: technologies; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.technologies (
    id integer NOT NULL,
    session_id integer,
    name text NOT NULL,
    field text NOT NULL,
    tier integer DEFAULT 1,
    description text,
    researched boolean DEFAULT false,
    research_progress integer DEFAULT 0,
    prerequisites jsonb DEFAULT '[]'::jsonb,
    unlocks jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT technologies_field_check CHECK ((field = ANY (ARRAY['physics'::text, 'society'::text, 'engineering'::text])))
);


--
-- Name: technologies_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.technologies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: technologies_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.technologies_id_seq OWNED BY maya_rp.technologies.id;


--
-- Name: tension_thresholds; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.tension_thresholds (
    id integer NOT NULL,
    name text NOT NULL,
    morale_min integer,
    morale_max integer,
    trigger_event text NOT NULL,
    description text
);


--
-- Name: tension_thresholds_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.tension_thresholds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tension_thresholds_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.tension_thresholds_id_seq OWNED BY maya_rp.tension_thresholds.id;


--
-- Name: terraforming_projects; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.terraforming_projects (
    id integer NOT NULL,
    planet_id integer,
    method character varying(50),
    progress_pct integer DEFAULT 0,
    required_resources jsonb,
    cost_credits integer DEFAULT 200000,
    started_at timestamp without time zone DEFAULT now(),
    status character varying(20) DEFAULT 'planned'::character varying,
    completed_at timestamp without time zone
);


--
-- Name: terraforming_projects_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.terraforming_projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: terraforming_projects_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.terraforming_projects_id_seq OWNED BY maya_rp.terraforming_projects.id;


--
-- Name: territory_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.territory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: territory_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.territory_id_seq OWNED BY maya_rp.territory.id;


--
-- Name: territory_modifiers; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.territory_modifiers (
    id integer NOT NULL,
    territory_id integer,
    modifier_type character varying(50) NOT NULL,
    value numeric NOT NULL,
    source_research_id integer,
    applied_at timestamp without time zone DEFAULT now()
);


--
-- Name: territory_modifiers_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.territory_modifiers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: territory_modifiers_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.territory_modifiers_id_seq OWNED BY maya_rp.territory_modifiers.id;


--
-- Name: territory_resources_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.territory_resources_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: territory_resources_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.territory_resources_id_seq OWNED BY maya_rp.territory_resources.id;


--
-- Name: theme_state; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.theme_state (
    session_id integer NOT NULL,
    themes_jsonb jsonb DEFAULT '[]'::jsonb,
    detected_at timestamp with time zone DEFAULT now()
);


--
-- Name: tick_summaries; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.tick_summaries (
    id integer NOT NULL,
    session_id integer NOT NULL,
    tick_number integer NOT NULL,
    categories jsonb DEFAULT '{}'::jsonb NOT NULL,
    events_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    formatted_bulletin text DEFAULT ''::text NOT NULL,
    ai_prose text,
    alerts_count integer DEFAULT 0,
    resource_snapshot jsonb,
    summary_for_telegram text,
    generated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tick_summaries_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.tick_summaries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tick_summaries_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.tick_summaries_id_seq OWNED BY maya_rp.tick_summaries.id;


--
-- Name: time_skip_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.time_skip_log (
    id integer NOT NULL,
    session_id integer DEFAULT 3 NOT NULL,
    days_skipped integer NOT NULL,
    focus character varying(50) DEFAULT 'balanced'::character varying,
    credits_before bigint,
    credits_after bigint,
    events_summary text[],
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: time_skip_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.time_skip_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: time_skip_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.time_skip_log_id_seq OWNED BY maya_rp.time_skip_log.id;


--
-- Name: trade_log; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.trade_log (
    id integer NOT NULL,
    route_id integer,
    quantity_shipped integer,
    revenue_generated bigint,
    happened_at timestamp without time zone DEFAULT now()
);


--
-- Name: trade_log_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.trade_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trade_log_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.trade_log_id_seq OWNED BY maya_rp.trade_log.id;


--
-- Name: trade_routes; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.trade_routes (
    id integer NOT NULL,
    session_id integer DEFAULT 3,
    origin_territory_id integer,
    destination_territory_id integer,
    resource_type character varying(50) NOT NULL,
    quantity_per_trip integer NOT NULL,
    price_per_unit numeric DEFAULT 100,
    frequency_days integer DEFAULT 7,
    active boolean DEFAULT true,
    last_run timestamp without time zone,
    resource_id integer
);


--
-- Name: trade_routes_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.trade_routes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trade_routes_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.trade_routes_id_seq OWNED BY maya_rp.trade_routes.id;


--
-- Name: training_programs; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.training_programs (
    id integer NOT NULL,
    name text,
    field text,
    duration integer DEFAULT 100,
    skill_bonus integer DEFAULT 5,
    graduates_receive text
);


--
-- Name: training_programs_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.training_programs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: training_programs_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.training_programs_id_seq OWNED BY maya_rp.training_programs.id;


--
-- Name: trait_assignments; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.trait_assignments (
    assignment_id integer NOT NULL,
    trait_id integer,
    target_type text,
    target_id integer,
    source text,
    intensity numeric DEFAULT 1.0,
    granted_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone
);


--
-- Name: trait_assignments_assignment_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.trait_assignments_assignment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trait_assignments_assignment_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.trait_assignments_assignment_id_seq OWNED BY maya_rp.trait_assignments.assignment_id;


--
-- Name: trait_catalog; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.trait_catalog (
    trait_id integer NOT NULL,
    name text NOT NULL,
    category text,
    target_type text,
    description text,
    effect_type text,
    effect_value numeric,
    appearance_modifier text,
    narrative_trigger text,
    stackable boolean DEFAULT false,
    tier_min integer DEFAULT 1,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: trait_catalog_trait_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.trait_catalog_trait_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trait_catalog_trait_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.trait_catalog_trait_id_seq OWNED BY maya_rp.trait_catalog.trait_id;


--
-- Name: transport_missions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.transport_missions (
    id integer NOT NULL,
    session_id integer,
    cargo_id integer,
    transport_ship_id integer,
    dest_type text,
    dest_id integer,
    status text DEFAULT 'in_transit'::text,
    depart_day integer,
    arrive_day integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: transport_missions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.transport_missions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: transport_missions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.transport_missions_id_seq OWNED BY maya_rp.transport_missions.id;


--
-- Name: treaties_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.treaties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: treaties_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.treaties_id_seq OWNED BY maya_rp.treaties.id;


--
-- Name: unified_dashboard; Type: VIEW; Schema: maya_rp; Owner: -
--

CREATE VIEW maya_rp.unified_dashboard AS
 SELECT id AS territory_id,
    system_name AS territory,
    population,
    tax_rate,
    development_level,
    crisis_level,
    ((((population)::numeric * tax_rate) * ((1)::numeric + (((development_level - 1))::numeric * 0.1))))::bigint AS daily_tax_revenue,
    trade_income,
    military_consumption,
    research_points,
    ( SELECT json_agg(json_build_object('resource', sr.name, 'quantity', ri.quantity)) AS json_agg
           FROM (maya_rp.resource_inventory ri
             JOIN maya_rp.strategic_resources sr ON ((sr.id = ri.resource_id)))
          WHERE (ri.quantity > 0)) AS inventory,
    ( SELECT json_agg(rp.name) AS json_agg
           FROM (maya_rp.research_queue rq
             JOIN maya_rp.research_projects rp ON ((rp.id = rq.project_id)))
          WHERE ((rq.status)::text = 'active'::text)) AS active_research
   FROM maya_rp.territory t
  WHERE (session_id = 3)
  ORDER BY system_name;


--
-- Name: university_campuses; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.university_campuses (
    id integer NOT NULL,
    name text,
    colony_id integer,
    research_rate numeric DEFAULT 1.0,
    level integer DEFAULT 1,
    prestige integer DEFAULT 0,
    territory_id integer,
    graduation_cycle_days integer DEFAULT 30,
    last_graduation_day integer DEFAULT 0
);


--
-- Name: university_campuses_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.university_campuses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: university_campuses_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.university_campuses_id_seq OWNED BY maya_rp.university_campuses.id;


--
-- Name: victory_tracking; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.victory_tracking (
    id integer NOT NULL,
    faction_id integer,
    victory_type character varying(50) NOT NULL,
    progress numeric DEFAULT 0,
    completed boolean DEFAULT false,
    completed_at timestamp without time zone,
    details jsonb
);


--
-- Name: victory_tracking_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.victory_tracking_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: victory_tracking_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.victory_tracking_id_seq OWNED BY maya_rp.victory_tracking.id;


--
-- Name: voyages; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.voyages (
    id integer NOT NULL,
    session_id integer NOT NULL,
    voyage_name text NOT NULL,
    origin text,
    destination text,
    distance_units numeric(12,3),
    distance_ly numeric(14,2),
    travel_hours numeric(14,2),
    travel_days numeric(8,3),
    depart_day integer,
    arrive_day integer,
    status text DEFAULT 'in_transit'::text NOT NULL,
    fleet_tag text,
    ship_count integer DEFAULT 0,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    arrived_at timestamp with time zone
);


--
-- Name: voyages_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.voyages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: voyages_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.voyages_id_seq OWNED BY maya_rp.voyages.id;


--
-- Name: war_exhaustion_effects; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.war_exhaustion_effects (
    id integer NOT NULL,
    campaign_id integer,
    morale_penalty integer DEFAULT 0,
    production_penalty integer DEFAULT 0,
    diplomatic_penalty integer DEFAULT 0,
    applied_at timestamp without time zone DEFAULT now()
);


--
-- Name: war_exhaustion_effects_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.war_exhaustion_effects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: war_exhaustion_effects_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.war_exhaustion_effects_id_seq OWNED BY maya_rp.war_exhaustion_effects.id;


--
-- Name: wars; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.wars (
    id integer NOT NULL,
    session_id integer,
    opponent_faction text,
    casus_belli text,
    war_goal text,
    phase text DEFAULT 'escalation'::text,
    status text DEFAULT 'active'::text,
    started_at_game_day integer,
    ended_at_game_day integer,
    attacker_casualties integer DEFAULT 0,
    defender_casualties integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: wars_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.wars_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wars_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.wars_id_seq OWNED BY maya_rp.wars.id;


--
-- Name: weapon_blueprints; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.weapon_blueprints (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    base_damage integer,
    base_range integer,
    slot_size character varying(10),
    tier_required integer DEFAULT 1,
    tech_prereq character varying(100),
    alloy_cost integer,
    credit_cost integer,
    research_cost integer,
    special_rules jsonb DEFAULT '[]'::jsonb
);


--
-- Name: weapon_blueprints_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.weapon_blueprints_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: weapon_blueprints_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.weapon_blueprints_id_seq OWNED BY maya_rp.weapon_blueprints.id;


--
-- Name: weapon_kinds; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.weapon_kinds (
    kind text NOT NULL,
    name text NOT NULL,
    description text,
    special_rules jsonb DEFAULT '{}'::jsonb
);


--
-- Name: weapon_upgrades; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.weapon_upgrades (
    id integer NOT NULL,
    weapon_id integer,
    upgrade_name character varying(100),
    effect_type character varying(50),
    effect_value double precision,
    tier_required integer,
    cost integer
);


--
-- Name: weapon_upgrades_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.weapon_upgrades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: weapon_upgrades_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.weapon_upgrades_id_seq OWNED BY maya_rp.weapon_upgrades.id;


--
-- Name: weapons; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.weapons (
    id integer NOT NULL,
    name text NOT NULL,
    kind text NOT NULL,
    slot_size text NOT NULL,
    damage integer NOT NULL,
    range_m integer NOT NULL,
    tier_min integer DEFAULT 1 NOT NULL,
    tier_max integer DEFAULT 8 NOT NULL,
    special_rules jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT weapons_slot_size_check CHECK ((slot_size = ANY (ARRAY['L'::text, 'M'::text, 'H'::text, 'XH'::text, 'SH'::text, 'WMD'::text])))
);


--
-- Name: weapons_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.weapons_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: weapons_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.weapons_id_seq OWNED BY maya_rp.weapons.id;


--
-- Name: wiki_articles; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.wiki_articles (
    id integer NOT NULL,
    session_id integer DEFAULT 3 NOT NULL,
    title character varying(200) NOT NULL,
    category character varying(50),
    tags text[],
    content text NOT NULL,
    source_file character varying(100),
    embedding public.vector(768),
    is_procedural boolean DEFAULT false,
    relevance_end_day integer,
    created_at timestamp with time zone DEFAULT now(),
    checkpoint_id integer,
    recorded_at_game_day integer
);


--
-- Name: wiki_articles_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.wiki_articles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wiki_articles_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.wiki_articles_id_seq OWNED BY maya_rp.wiki_articles.id;


--
-- Name: world_reactions; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.world_reactions (
    id integer NOT NULL,
    session_id integer,
    event_type character varying(50),
    reaction_type character varying(30),
    description text,
    source_faction character varying(50),
    target_faction character varying(50),
    surfaces_at_game_day integer,
    surfaced boolean DEFAULT false
);


--
-- Name: world_reactions_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.world_reactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: world_reactions_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.world_reactions_id_seq OWNED BY maya_rp.world_reactions.id;


--
-- Name: wreck_inventory; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.wreck_inventory (
    id integer NOT NULL,
    session_id integer,
    source_ship_id integer,
    name text,
    tier integer,
    hull integer,
    power_rating integer,
    sub_class text,
    acquired_at timestamp with time zone DEFAULT now(),
    status text DEFAULT 'available'::text
);


--
-- Name: wreck_inventory_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.wreck_inventory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wreck_inventory_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.wreck_inventory_id_seq OWNED BY maya_rp.wreck_inventory.id;


--
-- Name: yard_capacity; Type: TABLE; Schema: maya_rp; Owner: -
--

CREATE TABLE maya_rp.yard_capacity (
    id integer NOT NULL,
    yard_name text NOT NULL,
    location text,
    capital_slips integer DEFAULT 0 NOT NULL,
    medium_slips integer DEFAULT 0 NOT NULL,
    light_slips integer DEFAULT 0 NOT NULL,
    support_docks integer DEFAULT 0 NOT NULL,
    refit_bays integer DEFAULT 0 NOT NULL,
    total_capacity integer GENERATED ALWAYS AS (((((capital_slips + medium_slips) + light_slips) + support_docks) + refit_bays)) STORED,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    territory_id integer
);


--
-- Name: yard_capacity_id_seq; Type: SEQUENCE; Schema: maya_rp; Owner: -
--

CREATE SEQUENCE maya_rp.yard_capacity_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: yard_capacity_id_seq; Type: SEQUENCE OWNED BY; Schema: maya_rp; Owner: -
--

ALTER SEQUENCE maya_rp.yard_capacity_id_seq OWNED BY maya_rp.yard_capacity.id;


--
-- Name: _migrations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp._migrations ALTER COLUMN id SET DEFAULT nextval('maya_rp._migrations_id_seq'::regclass);


--
-- Name: academy_campuses id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.academy_campuses ALTER COLUMN id SET DEFAULT nextval('maya_rp.academy_campuses_id_seq'::regclass);


--
-- Name: active_disasters id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_disasters ALTER COLUMN id SET DEFAULT nextval('maya_rp.active_disasters_id_seq'::regclass);


--
-- Name: active_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.active_events_id_seq'::regclass);


--
-- Name: active_scenes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_scenes ALTER COLUMN id SET DEFAULT nextval('maya_rp.active_scenes_id_seq'::regclass);


--
-- Name: adjutant_prompts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.adjutant_prompts ALTER COLUMN id SET DEFAULT nextval('maya_rp.adjutant_prompts_id_seq'::regclass);


--
-- Name: ai_decision_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_decision_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.ai_decision_log_id_seq'::regclass);


--
-- Name: ai_decisions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_decisions ALTER COLUMN id SET DEFAULT nextval('maya_rp.ai_decisions_id_seq'::regclass);


--
-- Name: ai_tactics_history id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_tactics_history ALTER COLUMN id SET DEFAULT nextval('maya_rp.ai_tactics_history_id_seq'::regclass);


--
-- Name: alchemy_recipes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.alchemy_recipes ALTER COLUMN id SET DEFAULT nextval('maya_rp.alchemy_recipes_id_seq'::regclass);


--
-- Name: alert_queue id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.alert_queue ALTER COLUMN id SET DEFAULT nextval('maya_rp.alert_queue_id_seq'::regclass);


--
-- Name: animal_encounters id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.animal_encounters ALTER COLUMN id SET DEFAULT nextval('maya_rp.animal_encounters_id_seq'::regclass);


--
-- Name: anomalies_catalog id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.anomalies_catalog ALTER COLUMN id SET DEFAULT nextval('maya_rp.anomalies_catalog_id_seq'::regclass);


--
-- Name: anti_cloak_grids id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.anti_cloak_grids ALTER COLUMN id SET DEFAULT nextval('maya_rp.anti_cloak_grids_id_seq'::regclass);


--
-- Name: artifact_history id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.artifact_history ALTER COLUMN id SET DEFAULT nextval('maya_rp.artifact_history_id_seq'::regclass);


--
-- Name: artifacts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.artifacts ALTER COLUMN id SET DEFAULT nextval('maya_rp.artifacts_id_seq'::regclass);


--
-- Name: auto_queue id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.auto_queue ALTER COLUMN id SET DEFAULT nextval('maya_rp.auto_queue_id_seq'::regclass);


--
-- Name: battle_terrain id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.battle_terrain ALTER COLUMN id SET DEFAULT nextval('maya_rp.battle_terrain_id_seq'::regclass);


--
-- Name: bug_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.bug_events_id_seq'::regclass);


--
-- Name: bug_tech_tree id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_tech_tree ALTER COLUMN id SET DEFAULT nextval('maya_rp.bug_tech_tree_id_seq'::regclass);


--
-- Name: bug_war_assets id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_war_assets ALTER COLUMN id SET DEFAULT nextval('maya_rp.bug_war_assets_id_seq'::regclass);


--
-- Name: build_queue id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.build_queue ALTER COLUMN id SET DEFAULT nextval('maya_rp.build_queue_id_seq'::regclass);


--
-- Name: build_templates id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.build_templates ALTER COLUMN id SET DEFAULT nextval('maya_rp.build_templates_id_seq'::regclass);


--
-- Name: cabinet_decrees id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_decrees ALTER COLUMN id SET DEFAULT nextval('maya_rp.cabinet_decrees_id_seq'::regclass);


--
-- Name: cabinet_hierarchy id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_hierarchy ALTER COLUMN id SET DEFAULT nextval('maya_rp.cabinet_hierarchy_id_seq'::regclass);


--
-- Name: cabinet_meetings id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_meetings ALTER COLUMN id SET DEFAULT nextval('maya_rp.cabinet_meetings_id_seq'::regclass);


--
-- Name: cargo id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cargo ALTER COLUMN id SET DEFAULT nextval('maya_rp.cargo_id_seq'::regclass);


--
-- Name: chapters id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.chapters ALTER COLUMN id SET DEFAULT nextval('maya_rp.chapters_id_seq'::regclass);


--
-- Name: character_arcs id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_arcs ALTER COLUMN id SET DEFAULT nextval('maya_rp.character_arcs_id_seq'::regclass);


--
-- Name: character_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.character_events_id_seq'::regclass);


--
-- Name: character_injuries id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_injuries ALTER COLUMN id SET DEFAULT nextval('maya_rp.character_injuries_id_seq'::regclass);


--
-- Name: character_memories id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_memories ALTER COLUMN id SET DEFAULT nextval('maya_rp.character_memories_id_seq'::regclass);


--
-- Name: character_presence_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_presence_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.character_presence_log_id_seq'::regclass);


--
-- Name: character_quirks id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_quirks ALTER COLUMN id SET DEFAULT nextval('maya_rp.character_quirks_id_seq'::regclass);


--
-- Name: character_relationships id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_relationships ALTER COLUMN id SET DEFAULT nextval('maya_rp.character_relationships_id_seq'::regclass);


--
-- Name: character_traits id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_traits ALTER COLUMN id SET DEFAULT nextval('maya_rp.character_traits_id_seq'::regclass);


--
-- Name: characters id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.characters ALTER COLUMN id SET DEFAULT nextval('maya_rp.characters_id_seq'::regclass);


--
-- Name: chekhov_elements id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.chekhov_elements ALTER COLUMN id SET DEFAULT nextval('maya_rp.chekhov_elements_id_seq'::regclass);


--
-- Name: choices id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.choices ALTER COLUMN id SET DEFAULT nextval('maya_rp.choices_id_seq'::regclass);


--
-- Name: clues id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.clues ALTER COLUMN id SET DEFAULT nextval('maya_rp.clues_id_seq'::regclass);


--
-- Name: colonies id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.colonies ALTER COLUMN id SET DEFAULT nextval('maya_rp.colonies_id_seq'::regclass);


--
-- Name: colonization_projects id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.colonization_projects ALTER COLUMN id SET DEFAULT nextval('maya_rp.colonization_projects_id_seq'::regclass);


--
-- Name: combat_results id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_results ALTER COLUMN id SET DEFAULT nextval('maya_rp.combat_results_id_seq'::regclass);


--
-- Name: combat_rounds id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_rounds ALTER COLUMN id SET DEFAULT nextval('maya_rp.combat_rounds_id_seq'::regclass);


--
-- Name: combat_stats id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_stats ALTER COLUMN id SET DEFAULT nextval('maya_rp.combat_stats_id_seq'::regclass);


--
-- Name: commodities id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.commodities ALTER COLUMN id SET DEFAULT nextval('maya_rp.commodities_id_seq'::regclass);


--
-- Name: complaint_boxes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.complaint_boxes ALTER COLUMN id SET DEFAULT nextval('maya_rp.complaint_boxes_id_seq'::regclass);


--
-- Name: complaints id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.complaints ALTER COLUMN id SET DEFAULT nextval('maya_rp.complaints_id_seq'::regclass);


--
-- Name: consequence_seeds id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.consequence_seeds ALTER COLUMN id SET DEFAULT nextval('maya_rp.consequence_seeds_id_seq'::regclass);


--
-- Name: containment_measures id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.containment_measures ALTER COLUMN id SET DEFAULT nextval('maya_rp.containment_measures_id_seq'::regclass);


--
-- Name: conversation_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.conversation_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.conversation_log_id_seq'::regclass);


--
-- Name: corporate_assets id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporate_assets ALTER COLUMN id SET DEFAULT nextval('maya_rp.corporate_assets_id_seq'::regclass);


--
-- Name: corporate_contracts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporate_contracts ALTER COLUMN id SET DEFAULT nextval('maya_rp.corporate_contracts_id_seq'::regclass);


--
-- Name: corporations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporations ALTER COLUMN id SET DEFAULT nextval('maya_rp.corporations_id_seq'::regclass);


--
-- Name: counter_intel_ops id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.counter_intel_ops ALTER COLUMN id SET DEFAULT nextval('maya_rp.counter_intel_ops_id_seq'::regclass);


--
-- Name: crew_allocation_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_allocation_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.crew_allocation_log_id_seq'::regclass);


--
-- Name: crew_consumption_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_consumption_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.crew_consumption_log_id_seq'::regclass);


--
-- Name: crew_factions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_factions ALTER COLUMN id SET DEFAULT nextval('maya_rp.crew_factions_id_seq'::regclass);


--
-- Name: crew_production_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_production_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.crew_production_log_id_seq'::regclass);


--
-- Name: crew_roster id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_roster ALTER COLUMN id SET DEFAULT nextval('maya_rp.crew_roster_id_seq'::regclass);


--
-- Name: crew_skills id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_skills ALTER COLUMN id SET DEFAULT nextval('maya_rp.crew_skills_id_seq'::regclass);


--
-- Name: crew_xp_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_xp_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.crew_xp_log_id_seq'::regclass);


--
-- Name: crisis_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crisis_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.crisis_events_id_seq'::regclass);


--
-- Name: damage_resistances id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.damage_resistances ALTER COLUMN id SET DEFAULT nextval('maya_rp.damage_resistances_id_seq'::regclass);


--
-- Name: dark_ops id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.dark_ops ALTER COLUMN id SET DEFAULT nextval('maya_rp.dark_ops_id_seq'::regclass);


--
-- Name: defense_installations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.defense_installations ALTER COLUMN id SET DEFAULT nextval('maya_rp.defense_installations_id_seq'::regclass);


--
-- Name: difficulty_tiers id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.difficulty_tiers ALTER COLUMN id SET DEFAULT nextval('maya_rp.difficulty_tiers_id_seq'::regclass);


--
-- Name: dig_sites id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.dig_sites ALTER COLUMN id SET DEFAULT nextval('maya_rp.dig_sites_id_seq'::regclass);


--
-- Name: diplomatic_actions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.diplomatic_actions ALTER COLUMN id SET DEFAULT nextval('maya_rp.diplomatic_actions_id_seq'::regclass);


--
-- Name: disaster_templates id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.disaster_templates ALTER COLUMN id SET DEFAULT nextval('maya_rp.disaster_templates_id_seq'::regclass);


--
-- Name: discoveries id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.discoveries ALTER COLUMN id SET DEFAULT nextval('maya_rp.discoveries_id_seq'::regclass);


--
-- Name: duels id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.duels ALTER COLUMN id SET DEFAULT nextval('maya_rp.duels_id_seq'::regclass);


--
-- Name: economic_crises id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.economic_crises ALTER COLUMN id SET DEFAULT nextval('maya_rp.economic_crises_id_seq'::regclass);


--
-- Name: economic_tracker id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.economic_tracker ALTER COLUMN id SET DEFAULT nextval('maya_rp.economic_tracker_id_seq'::regclass);


--
-- Name: enrolled_crew id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.enrolled_crew ALTER COLUMN id SET DEFAULT nextval('maya_rp.enrolled_crew_id_seq'::regclass);


--
-- Name: envoys id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.envoys ALTER COLUMN id SET DEFAULT nextval('maya_rp.envoys_id_seq'::regclass);


--
-- Name: eradication_campaigns id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.eradication_campaigns ALTER COLUMN id SET DEFAULT nextval('maya_rp.eradication_campaigns_id_seq'::regclass);


--
-- Name: escape_countermeasures id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.escape_countermeasures ALTER COLUMN id SET DEFAULT nextval('maya_rp.escape_countermeasures_id_seq'::regclass);


--
-- Name: espionage_missions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.espionage_missions ALTER COLUMN id SET DEFAULT nextval('maya_rp.espionage_missions_id_seq'::regclass);


--
-- Name: espionage_operations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.espionage_operations ALTER COLUMN id SET DEFAULT nextval('maya_rp.espionage_operations_id_seq'::regclass);


--
-- Name: event_templates id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.event_templates ALTER COLUMN id SET DEFAULT nextval('maya_rp.event_templates_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.events ALTER COLUMN id SET DEFAULT nextval('maya_rp.events_id_seq'::regclass);


--
-- Name: faction_ai_state id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_ai_state ALTER COLUMN id SET DEFAULT nextval('maya_rp.faction_ai_state_id_seq'::regclass);


--
-- Name: faction_policies id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_policies ALTER COLUMN id SET DEFAULT nextval('maya_rp.faction_policies_id_seq'::regclass);


--
-- Name: faction_relations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_relations ALTER COLUMN id SET DEFAULT nextval('maya_rp.faction_relations_id_seq'::regclass);


--
-- Name: faction_ships id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_ships ALTER COLUMN id SET DEFAULT nextval('maya_rp.faction_ships_id_seq'::regclass);


--
-- Name: faction_slave_policy id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_slave_policy ALTER COLUMN id SET DEFAULT nextval('maya_rp.faction_slave_policy_id_seq'::regclass);


--
-- Name: faction_species_rights id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_species_rights ALTER COLUMN id SET DEFAULT nextval('maya_rp.faction_species_rights_id_seq'::regclass);


--
-- Name: faction_trade_deals id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_trade_deals ALTER COLUMN id SET DEFAULT nextval('maya_rp.faction_trade_deals_id_seq'::regclass);


--
-- Name: factions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.factions ALTER COLUMN id SET DEFAULT nextval('maya_rp.factions_id_seq'::regclass);


--
-- Name: family_relations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.family_relations ALTER COLUMN id SET DEFAULT nextval('maya_rp.family_relations_id_seq'::regclass);


--
-- Name: fleet_formations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleet_formations ALTER COLUMN id SET DEFAULT nextval('maya_rp.fleet_formations_id_seq'::regclass);


--
-- Name: fleet_members id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleet_members ALTER COLUMN id SET DEFAULT nextval('maya_rp.fleet_members_id_seq'::regclass);


--
-- Name: fleets id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleets ALTER COLUMN id SET DEFAULT nextval('maya_rp.fleets_id_seq'::regclass);


--
-- Name: global_modifiers id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.global_modifiers ALTER COLUMN id SET DEFAULT nextval('maya_rp.global_modifiers_id_seq'::regclass);


--
-- Name: governance_projects id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.governance_projects ALTER COLUMN id SET DEFAULT nextval('maya_rp.governance_projects_id_seq'::regclass);


--
-- Name: governor_applicants id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.governor_applicants ALTER COLUMN id SET DEFAULT nextval('maya_rp.governor_applicants_id_seq'::regclass);


--
-- Name: grand_plan id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.grand_plan ALTER COLUMN id SET DEFAULT nextval('maya_rp.grand_plan_id_seq'::regclass);


--
-- Name: guardrail_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.guardrail_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.guardrail_log_id_seq'::regclass);


--
-- Name: horror_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.horror_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.horror_events_id_seq'::regclass);


--
-- Name: image_generations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.image_generations ALTER COLUMN id SET DEFAULT nextval('maya_rp.image_generations_id_seq'::regclass);


--
-- Name: image_prompts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.image_prompts ALTER COLUMN id SET DEFAULT nextval('maya_rp.image_prompts_id_seq'::regclass);


--
-- Name: incoming_raids id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.incoming_raids ALTER COLUMN id SET DEFAULT nextval('maya_rp.incoming_raids_id_seq'::regclass);


--
-- Name: infestation_instances id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_instances ALTER COLUMN id SET DEFAULT nextval('maya_rp.infestation_instances_id_seq'::regclass);


--
-- Name: infestation_stages id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_stages ALTER COLUMN id SET DEFAULT nextval('maya_rp.infestation_stages_id_seq'::regclass);


--
-- Name: infrastructure_instances id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_instances ALTER COLUMN id SET DEFAULT nextval('maya_rp.infrastructure_instances_id_seq'::regclass);


--
-- Name: infrastructure_production id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_production ALTER COLUMN id SET DEFAULT nextval('maya_rp.infrastructure_production_id_seq'::regclass);


--
-- Name: infrastructure_types id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_types ALTER COLUMN id SET DEFAULT nextval('maya_rp.infrastructure_types_id_seq'::regclass);


--
-- Name: intel_reports id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.intel_reports ALTER COLUMN id SET DEFAULT nextval('maya_rp.intel_reports_id_seq'::regclass);


--
-- Name: interrogation_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.interrogation_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.interrogation_log_id_seq'::regclass);


--
-- Name: intimacy_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.intimacy_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.intimacy_events_id_seq'::regclass);


--
-- Name: investigation_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.investigation_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.investigation_log_id_seq'::regclass);


--
-- Name: investigations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.investigations ALTER COLUMN id SET DEFAULT nextval('maya_rp.investigations_id_seq'::regclass);


--
-- Name: jealousy_states id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.jealousy_states ALTER COLUMN id SET DEFAULT nextval('maya_rp.jealousy_states_id_seq'::regclass);


--
-- Name: leader_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.leader_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.leader_events_id_seq'::regclass);


--
-- Name: leaders id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.leaders ALTER COLUMN id SET DEFAULT nextval('maya_rp.leaders_id_seq'::regclass);


--
-- Name: legendary_artifacts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.legendary_artifacts ALTER COLUMN id SET DEFAULT nextval('maya_rp.legendary_artifacts_id_seq'::regclass);


--
-- Name: legio_structure id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.legio_structure ALTER COLUMN id SET DEFAULT nextval('maya_rp.legio_structure_id_seq'::regclass);


--
-- Name: locations id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.locations ALTER COLUMN id SET DEFAULT nextval('maya_rp.locations_id_seq'::regclass);


--
-- Name: material_stockpiles id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.material_stockpiles ALTER COLUMN id SET DEFAULT nextval('maya_rp.material_stockpiles_id_seq'::regclass);


--
-- Name: materials id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.materials ALTER COLUMN id SET DEFAULT nextval('maya_rp.materials_id_seq'::regclass);


--
-- Name: megastructure_construction id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_construction ALTER COLUMN id SET DEFAULT nextval('maya_rp.megastructure_construction_id_seq'::regclass);


--
-- Name: megastructure_types id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_types ALTER COLUMN id SET DEFAULT nextval('maya_rp.megastructure_types_id_seq'::regclass);


--
-- Name: migration_versions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.migration_versions ALTER COLUMN id SET DEFAULT nextval('maya_rp.migration_versions_id_seq'::regclass);


--
-- Name: military_expenditure id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.military_expenditure ALTER COLUMN id SET DEFAULT nextval('maya_rp.military_expenditure_id_seq'::regclass);


--
-- Name: modules id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.modules ALTER COLUMN id SET DEFAULT nextval('maya_rp.modules_id_seq'::regclass);


--
-- Name: morale_history id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.morale_history ALTER COLUMN id SET DEFAULT nextval('maya_rp.morale_history_id_seq'::regclass);


--
-- Name: morality_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.morality_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.morality_log_id_seq'::regclass);


--
-- Name: mystery_templates id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.mystery_templates ALTER COLUMN id SET DEFAULT nextval('maya_rp.mystery_templates_id_seq'::regclass);


--
-- Name: narrative_hooks id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrative_hooks ALTER COLUMN id SET DEFAULT nextval('maya_rp.narrative_hooks_id_seq'::regclass);


--
-- Name: narrative_seeds id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrative_seeds ALTER COLUMN id SET DEFAULT nextval('maya_rp.narrative_seeds_id_seq'::regclass);


--
-- Name: narrator_cost_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrator_cost_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.narrator_cost_log_id_seq'::regclass);


--
-- Name: news_articles id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.news_articles ALTER COLUMN id SET DEFAULT nextval('maya_rp.news_articles_id_seq'::regclass);


--
-- Name: novel_chunks id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.novel_chunks ALTER COLUMN id SET DEFAULT nextval('maya_rp.novel_chunks_id_seq'::regclass);


--
-- Name: npc_offscreen_interactions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.npc_offscreen_interactions ALTER COLUMN id SET DEFAULT nextval('maya_rp.npc_offscreen_interactions_id_seq'::regclass);


--
-- Name: objectives id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.objectives ALTER COLUMN id SET DEFAULT nextval('maya_rp.objectives_id_seq'::regclass);


--
-- Name: pirate_activities id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_activities ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_activities_id_seq'::regclass);


--
-- Name: pirate_alerts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_alerts ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_alerts_id_seq'::regclass);


--
-- Name: pirate_artifacts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_artifacts ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_artifacts_id_seq'::regclass);


--
-- Name: pirate_bases id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_bases ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_bases_id_seq'::regclass);


--
-- Name: pirate_bounties id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_bounties ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_bounties_id_seq'::regclass);


--
-- Name: pirate_extortion id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_extortion ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_extortion_id_seq'::regclass);


--
-- Name: pirate_fleet_templates id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_fleet_templates ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_fleet_templates_id_seq'::regclass);


--
-- Name: pirate_loot_tables id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_loot_tables ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_loot_tables_id_seq'::regclass);


--
-- Name: pirate_raids id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_raids ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_raids_id_seq'::regclass);


--
-- Name: pirate_salvage_templates id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_salvage_templates ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_salvage_templates_id_seq'::regclass);


--
-- Name: pirate_ship_classes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_ship_classes ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_ship_classes_id_seq'::regclass);


--
-- Name: pirate_zones id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_zones ALTER COLUMN id SET DEFAULT nextval('maya_rp.pirate_zones_id_seq'::regclass);


--
-- Name: planet_features id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_features ALTER COLUMN id SET DEFAULT nextval('maya_rp.planet_features_id_seq'::regclass);


--
-- Name: planet_population id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_population ALTER COLUMN id SET DEFAULT nextval('maya_rp.planet_population_id_seq'::regclass);


--
-- Name: planets id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planets ALTER COLUMN id SET DEFAULT nextval('maya_rp.planets_id_seq'::regclass);


--
-- Name: player_action_catalog id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_action_catalog ALTER COLUMN id SET DEFAULT nextval('maya_rp.player_action_catalog_id_seq'::regclass);


--
-- Name: player_action_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_action_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.player_action_log_id_seq'::regclass);


--
-- Name: player_trades id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_trades ALTER COLUMN id SET DEFAULT nextval('maya_rp.player_trades_id_seq'::regclass);


--
-- Name: policy_catalog id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.policy_catalog ALTER COLUMN id SET DEFAULT nextval('maya_rp.policy_catalog_id_seq'::regclass);


--
-- Name: policy_registry id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.policy_registry ALTER COLUMN id SET DEFAULT nextval('maya_rp.policy_registry_id_seq'::regclass);


--
-- Name: political_factions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.political_factions ALTER COLUMN id SET DEFAULT nextval('maya_rp.political_factions_id_seq'::regclass);


--
-- Name: population_sentiment id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.population_sentiment ALTER COLUMN id SET DEFAULT nextval('maya_rp.population_sentiment_id_seq'::regclass);


--
-- Name: port_types id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.port_types ALTER COLUMN id SET DEFAULT nextval('maya_rp.port_types_id_seq'::regclass);


--
-- Name: port_upgrades id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.port_upgrades ALTER COLUMN id SET DEFAULT nextval('maya_rp.port_upgrades_id_seq'::regclass);


--
-- Name: ports id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ports ALTER COLUMN id SET DEFAULT nextval('maya_rp.ports_id_seq'::regclass);


--
-- Name: pregnancies id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pregnancies ALTER COLUMN id SET DEFAULT nextval('maya_rp.pregnancies_id_seq'::regclass);


--
-- Name: price_history id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.price_history ALTER COLUMN id SET DEFAULT nextval('maya_rp.price_history_id_seq'::regclass);


--
-- Name: prisoner_intel_pipeline id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.prisoner_intel_pipeline ALTER COLUMN id SET DEFAULT nextval('maya_rp.prisoner_intel_pipeline_id_seq'::regclass);


--
-- Name: prisoners id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.prisoners ALTER COLUMN id SET DEFAULT nextval('maya_rp.prisoners_id_seq'::regclass);


--
-- Name: production_consumption_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_consumption_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.production_consumption_log_id_seq'::regclass);


--
-- Name: production_lines id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_lines ALTER COLUMN id SET DEFAULT nextval('maya_rp.production_lines_id_seq'::regclass);


--
-- Name: production_queue id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_queue ALTER COLUMN id SET DEFAULT nextval('maya_rp.production_queue_id_seq'::regclass);


--
-- Name: production_requirements id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_requirements ALTER COLUMN id SET DEFAULT nextval('maya_rp.production_requirements_id_seq'::regclass);


--
-- Name: propaganda_campaigns id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.propaganda_campaigns ALTER COLUMN id SET DEFAULT nextval('maya_rp.propaganda_campaigns_id_seq'::regclass);


--
-- Name: public_opinion id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.public_opinion ALTER COLUMN id SET DEFAULT nextval('maya_rp.public_opinion_id_seq'::regclass);


--
-- Name: quarterly_tasks id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.quarterly_tasks ALTER COLUMN id SET DEFAULT nextval('maya_rp.quarterly_tasks_id_seq'::regclass);


--
-- Name: quests id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.quests ALTER COLUMN id SET DEFAULT nextval('maya_rp.quests_id_seq'::regclass);


--
-- Name: raid_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.raid_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.raid_log_id_seq'::regclass);


--
-- Name: recipes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.recipes ALTER COLUMN id SET DEFAULT nextval('maya_rp.recipes_id_seq'::regclass);


--
-- Name: refill_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.refill_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.refill_log_id_seq'::regclass);


--
-- Name: reputation_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.reputation_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.reputation_events_id_seq'::regclass);


--
-- Name: research_labs id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.research_labs ALTER COLUMN id SET DEFAULT nextval('maya_rp.research_labs_id_seq'::regclass);


--
-- Name: research_projects id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.research_projects ALTER COLUMN id SET DEFAULT nextval('maya_rp.research_projects_id_seq'::regclass);


--
-- Name: research_queue id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.research_queue ALTER COLUMN id SET DEFAULT nextval('maya_rp.research_queue_id_seq'::regclass);


--
-- Name: roll_history id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_history ALTER COLUMN id SET DEFAULT nextval('maya_rp.roll_history_id_seq'::regclass);


--
-- Name: roll_outcome_tiers id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_outcome_tiers ALTER COLUMN id SET DEFAULT nextval('maya_rp.roll_outcome_tiers_id_seq'::regclass);


--
-- Name: roll_types id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_types ALTER COLUMN id SET DEFAULT nextval('maya_rp.roll_types_id_seq'::regclass);


--
-- Name: romance_arcs id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.romance_arcs ALTER COLUMN id SET DEFAULT nextval('maya_rp.romance_arcs_id_seq'::regclass);


--
-- Name: romance_tiers id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.romance_tiers ALTER COLUMN id SET DEFAULT nextval('maya_rp.romance_tiers_id_seq'::regclass);


--
-- Name: royal_accounts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.royal_accounts ALTER COLUMN id SET DEFAULT nextval('maya_rp.royal_accounts_id_seq'::regclass);


--
-- Name: royal_offspring id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.royal_offspring ALTER COLUMN id SET DEFAULT nextval('maya_rp.royal_offspring_id_seq'::regclass);


--
-- Name: savepoints id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.savepoints ALTER COLUMN id SET DEFAULT nextval('maya_rp.savepoints_id_seq'::regclass);


--
-- Name: scene_stack id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scene_stack ALTER COLUMN id SET DEFAULT nextval('maya_rp.scene_stack_id_seq'::regclass);


--
-- Name: science_missions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.science_missions ALTER COLUMN id SET DEFAULT nextval('maya_rp.science_missions_id_seq'::regclass);


--
-- Name: scientific_theories id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scientific_theories ALTER COLUMN id SET DEFAULT nextval('maya_rp.scientific_theories_id_seq'::regclass);


--
-- Name: scientist_assignments id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scientist_assignments ALTER COLUMN id SET DEFAULT nextval('maya_rp.scientist_assignments_id_seq'::regclass);


--
-- Name: score_history id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.score_history ALTER COLUMN id SET DEFAULT nextval('maya_rp.score_history_id_seq'::regclass);


--
-- Name: secrets id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.secrets ALTER COLUMN id SET DEFAULT nextval('maya_rp.secrets_id_seq'::regclass);


--
-- Name: sector_connections id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_connections ALTER COLUMN id SET DEFAULT nextval('maya_rp.sector_connections_id_seq'::regclass);


--
-- Name: sector_resources id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_resources ALTER COLUMN id SET DEFAULT nextval('maya_rp.sector_resources_id_seq'::regclass);


--
-- Name: sector_visibility id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_visibility ALTER COLUMN id SET DEFAULT nextval('maya_rp.sector_visibility_id_seq'::regclass);


--
-- Name: sectors id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sectors ALTER COLUMN id SET DEFAULT nextval('maya_rp.sectors_id_seq'::regclass);


--
-- Name: sessions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sessions ALTER COLUMN id SET DEFAULT nextval('maya_rp.sessions_id_seq'::regclass);


--
-- Name: ship_armaments id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_armaments ALTER COLUMN id SET DEFAULT nextval('maya_rp.ship_armaments_id_seq'::regclass);


--
-- Name: ship_classes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_classes ALTER COLUMN id SET DEFAULT nextval('maya_rp.ship_classes_id_seq'::regclass);


--
-- Name: ship_modules id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_modules ALTER COLUMN id SET DEFAULT nextval('maya_rp.ship_modules_id_seq'::regclass);


--
-- Name: ship_roles id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_roles ALTER COLUMN id SET DEFAULT nextval('maya_rp.ship_roles_id_seq'::regclass);


--
-- Name: ship_sub_classes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_sub_classes ALTER COLUMN id SET DEFAULT nextval('maya_rp.ship_sub_classes_id_seq'::regclass);


--
-- Name: ship_tech_bonuses id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_tech_bonuses ALTER COLUMN id SET DEFAULT nextval('maya_rp.ship_tech_bonuses_id_seq'::regclass);


--
-- Name: ships id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ships ALTER COLUMN id SET DEFAULT nextval('maya_rp.ships_id_seq'::regclass);


--
-- Name: sieges id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sieges ALTER COLUMN id SET DEFAULT nextval('maya_rp.sieges_id_seq'::regclass);


--
-- Name: slave_births id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_births ALTER COLUMN id SET DEFAULT nextval('maya_rp.slave_births_id_seq'::regclass);


--
-- Name: slave_market id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_market ALTER COLUMN id SET DEFAULT nextval('maya_rp.slave_market_id_seq'::regclass);


--
-- Name: slave_revolts id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_revolts ALTER COLUMN id SET DEFAULT nextval('maya_rp.slave_revolts_id_seq'::regclass);


--
-- Name: slave_training id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_training ALTER COLUMN id SET DEFAULT nextval('maya_rp.slave_training_id_seq'::regclass);


--
-- Name: slaves id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slaves ALTER COLUMN id SET DEFAULT nextval('maya_rp.slaves_id_seq'::regclass);


--
-- Name: social_events id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.social_events ALTER COLUMN id SET DEFAULT nextval('maya_rp.social_events_id_seq'::regclass);


--
-- Name: social_templates id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.social_templates ALTER COLUMN id SET DEFAULT nextval('maya_rp.social_templates_id_seq'::regclass);


--
-- Name: space_animals id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.space_animals ALTER COLUMN id SET DEFAULT nextval('maya_rp.space_animals_id_seq'::regclass);


--
-- Name: space_anomalies id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.space_anomalies ALTER COLUMN id SET DEFAULT nextval('maya_rp.space_anomalies_id_seq'::regclass);


--
-- Name: space_lanes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.space_lanes ALTER COLUMN id SET DEFAULT nextval('maya_rp.space_lanes_id_seq'::regclass);


--
-- Name: species_catalog id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.species_catalog ALTER COLUMN id SET DEFAULT nextval('maya_rp.species_catalog_id_seq'::regclass);


--
-- Name: spy_networks id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.spy_networks ALTER COLUMN id SET DEFAULT nextval('maya_rp.spy_networks_id_seq'::regclass);


--
-- Name: standing_orders id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.standing_orders ALTER COLUMN id SET DEFAULT nextval('maya_rp.standing_orders_id_seq'::regclass);


--
-- Name: state_snapshots id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.state_snapshots ALTER COLUMN id SET DEFAULT nextval('maya_rp.state_snapshots_id_seq'::regclass);


--
-- Name: stealth_unit_types id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stealth_unit_types ALTER COLUMN id SET DEFAULT nextval('maya_rp.stealth_unit_types_id_seq'::regclass);


--
-- Name: stealth_units id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stealth_units ALTER COLUMN id SET DEFAULT nextval('maya_rp.stealth_units_id_seq'::regclass);


--
-- Name: story_arcs id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_arcs ALTER COLUMN id SET DEFAULT nextval('maya_rp.story_arcs_id_seq'::regclass);


--
-- Name: story_checkpoints id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_checkpoints ALTER COLUMN id SET DEFAULT nextval('maya_rp.story_checkpoints_id_seq'::regclass);


--
-- Name: story_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.story_log_id_seq'::regclass);


--
-- Name: strategic_resources id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.strategic_resources ALTER COLUMN id SET DEFAULT nextval('maya_rp.strategic_resources_id_seq'::regclass);


--
-- Name: stream_templates id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stream_templates ALTER COLUMN id SET DEFAULT nextval('maya_rp.stream_templates_id_seq'::regclass);


--
-- Name: supply_depots id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.supply_depots ALTER COLUMN id SET DEFAULT nextval('maya_rp.supply_depots_id_seq'::regclass);


--
-- Name: supply_lines id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.supply_lines ALTER COLUMN id SET DEFAULT nextval('maya_rp.supply_lines_id_seq'::regclass);


--
-- Name: tactical_states id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tactical_states ALTER COLUMN id SET DEFAULT nextval('maya_rp.tactical_states_id_seq'::regclass);


--
-- Name: tactics_catalog id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tactics_catalog ALTER COLUMN id SET DEFAULT nextval('maya_rp.tactics_catalog_id_seq'::regclass);


--
-- Name: talent_catalog id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.talent_catalog ALTER COLUMN id SET DEFAULT nextval('maya_rp.talent_catalog_id_seq'::regclass);


--
-- Name: task_routes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.task_routes ALTER COLUMN id SET DEFAULT nextval('maya_rp.task_routes_id_seq'::regclass);


--
-- Name: tax_history id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tax_history ALTER COLUMN id SET DEFAULT nextval('maya_rp.tax_history_id_seq'::regclass);


--
-- Name: technologies id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.technologies ALTER COLUMN id SET DEFAULT nextval('maya_rp.technologies_id_seq'::regclass);


--
-- Name: tension_thresholds id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tension_thresholds ALTER COLUMN id SET DEFAULT nextval('maya_rp.tension_thresholds_id_seq'::regclass);


--
-- Name: terraforming_projects id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.terraforming_projects ALTER COLUMN id SET DEFAULT nextval('maya_rp.terraforming_projects_id_seq'::regclass);


--
-- Name: territory id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory ALTER COLUMN id SET DEFAULT nextval('maya_rp.territory_id_seq'::regclass);


--
-- Name: territory_modifiers id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory_modifiers ALTER COLUMN id SET DEFAULT nextval('maya_rp.territory_modifiers_id_seq'::regclass);


--
-- Name: territory_resources id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory_resources ALTER COLUMN id SET DEFAULT nextval('maya_rp.territory_resources_id_seq'::regclass);


--
-- Name: tick_summaries id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tick_summaries ALTER COLUMN id SET DEFAULT nextval('maya_rp.tick_summaries_id_seq'::regclass);


--
-- Name: time_skip_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.time_skip_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.time_skip_log_id_seq'::regclass);


--
-- Name: trade_log id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trade_log ALTER COLUMN id SET DEFAULT nextval('maya_rp.trade_log_id_seq'::regclass);


--
-- Name: trade_routes id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trade_routes ALTER COLUMN id SET DEFAULT nextval('maya_rp.trade_routes_id_seq'::regclass);


--
-- Name: training_programs id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.training_programs ALTER COLUMN id SET DEFAULT nextval('maya_rp.training_programs_id_seq'::regclass);


--
-- Name: trait_assignments assignment_id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trait_assignments ALTER COLUMN assignment_id SET DEFAULT nextval('maya_rp.trait_assignments_assignment_id_seq'::regclass);


--
-- Name: trait_catalog trait_id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trait_catalog ALTER COLUMN trait_id SET DEFAULT nextval('maya_rp.trait_catalog_trait_id_seq'::regclass);


--
-- Name: transport_missions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.transport_missions ALTER COLUMN id SET DEFAULT nextval('maya_rp.transport_missions_id_seq'::regclass);


--
-- Name: treaties id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.treaties ALTER COLUMN id SET DEFAULT nextval('maya_rp.treaties_id_seq'::regclass);


--
-- Name: university_campuses id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.university_campuses ALTER COLUMN id SET DEFAULT nextval('maya_rp.university_campuses_id_seq'::regclass);


--
-- Name: victory_tracking id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.victory_tracking ALTER COLUMN id SET DEFAULT nextval('maya_rp.victory_tracking_id_seq'::regclass);


--
-- Name: voyages id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.voyages ALTER COLUMN id SET DEFAULT nextval('maya_rp.voyages_id_seq'::regclass);


--
-- Name: war_exhaustion_effects id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.war_exhaustion_effects ALTER COLUMN id SET DEFAULT nextval('maya_rp.war_exhaustion_effects_id_seq'::regclass);


--
-- Name: wars id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.wars ALTER COLUMN id SET DEFAULT nextval('maya_rp.wars_id_seq'::regclass);


--
-- Name: weapon_blueprints id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapon_blueprints ALTER COLUMN id SET DEFAULT nextval('maya_rp.weapon_blueprints_id_seq'::regclass);


--
-- Name: weapon_upgrades id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapon_upgrades ALTER COLUMN id SET DEFAULT nextval('maya_rp.weapon_upgrades_id_seq'::regclass);


--
-- Name: weapons id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapons ALTER COLUMN id SET DEFAULT nextval('maya_rp.weapons_id_seq'::regclass);


--
-- Name: wiki_articles id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.wiki_articles ALTER COLUMN id SET DEFAULT nextval('maya_rp.wiki_articles_id_seq'::regclass);


--
-- Name: world_reactions id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.world_reactions ALTER COLUMN id SET DEFAULT nextval('maya_rp.world_reactions_id_seq'::regclass);


--
-- Name: wreck_inventory id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.wreck_inventory ALTER COLUMN id SET DEFAULT nextval('maya_rp.wreck_inventory_id_seq'::regclass);


--
-- Name: yard_capacity id; Type: DEFAULT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.yard_capacity ALTER COLUMN id SET DEFAULT nextval('maya_rp.yard_capacity_id_seq'::regclass);


--
-- Name: _migrations _migrations_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp._migrations
    ADD CONSTRAINT _migrations_name_key UNIQUE (name);


--
-- Name: _migrations _migrations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp._migrations
    ADD CONSTRAINT _migrations_pkey PRIMARY KEY (id);


--
-- Name: academy_campuses academy_campuses_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.academy_campuses
    ADD CONSTRAINT academy_campuses_pkey PRIMARY KEY (id);


--
-- Name: active_disasters active_disasters_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_disasters
    ADD CONSTRAINT active_disasters_pkey PRIMARY KEY (id);


--
-- Name: active_events active_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_events
    ADD CONSTRAINT active_events_pkey PRIMARY KEY (id);


--
-- Name: active_scenes active_scenes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_scenes
    ADD CONSTRAINT active_scenes_pkey PRIMARY KEY (id);


--
-- Name: adjutant_prompts adjutant_prompts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.adjutant_prompts
    ADD CONSTRAINT adjutant_prompts_pkey PRIMARY KEY (id);


--
-- Name: ai_decision_log ai_decision_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_decision_log
    ADD CONSTRAINT ai_decision_log_pkey PRIMARY KEY (id);


--
-- Name: ai_decisions ai_decisions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_decisions
    ADD CONSTRAINT ai_decisions_pkey PRIMARY KEY (id);


--
-- Name: ai_tactics_history ai_tactics_history_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_tactics_history
    ADD CONSTRAINT ai_tactics_history_pkey PRIMARY KEY (id);


--
-- Name: alchemy_recipes alchemy_recipes_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.alchemy_recipes
    ADD CONSTRAINT alchemy_recipes_name_key UNIQUE (name);


--
-- Name: alchemy_recipes alchemy_recipes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.alchemy_recipes
    ADD CONSTRAINT alchemy_recipes_pkey PRIMARY KEY (id);


--
-- Name: alert_queue alert_queue_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.alert_queue
    ADD CONSTRAINT alert_queue_pkey PRIMARY KEY (id);


--
-- Name: animal_encounters animal_encounters_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.animal_encounters
    ADD CONSTRAINT animal_encounters_pkey PRIMARY KEY (id);


--
-- Name: anomalies_catalog anomalies_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.anomalies_catalog
    ADD CONSTRAINT anomalies_catalog_pkey PRIMARY KEY (id);


--
-- Name: anti_cloak_grids anti_cloak_grids_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.anti_cloak_grids
    ADD CONSTRAINT anti_cloak_grids_pkey PRIMARY KEY (id);


--
-- Name: artifact_history artifact_history_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.artifact_history
    ADD CONSTRAINT artifact_history_pkey PRIMARY KEY (id);


--
-- Name: artifacts artifacts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.artifacts
    ADD CONSTRAINT artifacts_pkey PRIMARY KEY (id);


--
-- Name: auto_queue auto_queue_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.auto_queue
    ADD CONSTRAINT auto_queue_pkey PRIMARY KEY (id);


--
-- Name: battle_terrain battle_terrain_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.battle_terrain
    ADD CONSTRAINT battle_terrain_pkey PRIMARY KEY (id);


--
-- Name: bug_events bug_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_events
    ADD CONSTRAINT bug_events_pkey PRIMARY KEY (id);


--
-- Name: bug_tech_tree bug_tech_tree_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_tech_tree
    ADD CONSTRAINT bug_tech_tree_name_key UNIQUE (name);


--
-- Name: bug_tech_tree bug_tech_tree_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_tech_tree
    ADD CONSTRAINT bug_tech_tree_pkey PRIMARY KEY (id);


--
-- Name: bug_war_assets bug_war_assets_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_war_assets
    ADD CONSTRAINT bug_war_assets_name_key UNIQUE (name);


--
-- Name: bug_war_assets bug_war_assets_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_war_assets
    ADD CONSTRAINT bug_war_assets_pkey PRIMARY KEY (id);


--
-- Name: build_queue build_queue_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.build_queue
    ADD CONSTRAINT build_queue_pkey PRIMARY KEY (id);


--
-- Name: build_templates build_templates_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.build_templates
    ADD CONSTRAINT build_templates_pkey PRIMARY KEY (id);


--
-- Name: cabinet_decrees cabinet_decrees_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_decrees
    ADD CONSTRAINT cabinet_decrees_pkey PRIMARY KEY (id);


--
-- Name: cabinet_hierarchy cabinet_hierarchy_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_hierarchy
    ADD CONSTRAINT cabinet_hierarchy_pkey PRIMARY KEY (id);


--
-- Name: cabinet_hierarchy cabinet_hierarchy_session_id_title_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_hierarchy
    ADD CONSTRAINT cabinet_hierarchy_session_id_title_key UNIQUE (session_id, title);


--
-- Name: cabinet_meetings cabinet_meetings_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_meetings
    ADD CONSTRAINT cabinet_meetings_pkey PRIMARY KEY (id);


--
-- Name: cargo cargo_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cargo
    ADD CONSTRAINT cargo_pkey PRIMARY KEY (id);


--
-- Name: chapters chapters_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.chapters
    ADD CONSTRAINT chapters_pkey PRIMARY KEY (id);


--
-- Name: chapters chapters_session_id_chapter_number_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.chapters
    ADD CONSTRAINT chapters_session_id_chapter_number_key UNIQUE (session_id, chapter_number);


--
-- Name: character_arcs character_arcs_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_arcs
    ADD CONSTRAINT character_arcs_pkey PRIMARY KEY (id);


--
-- Name: character_events character_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_events
    ADD CONSTRAINT character_events_pkey PRIMARY KEY (id);


--
-- Name: character_injuries character_injuries_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_injuries
    ADD CONSTRAINT character_injuries_pkey PRIMARY KEY (id);


--
-- Name: character_memories character_memories_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_memories
    ADD CONSTRAINT character_memories_pkey PRIMARY KEY (id);


--
-- Name: character_presence_log character_presence_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_presence_log
    ADD CONSTRAINT character_presence_log_pkey PRIMARY KEY (id);


--
-- Name: character_quirks character_quirks_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_quirks
    ADD CONSTRAINT character_quirks_pkey PRIMARY KEY (id);


--
-- Name: character_relationships character_relationships_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_relationships
    ADD CONSTRAINT character_relationships_pkey PRIMARY KEY (id);


--
-- Name: character_relationships character_relationships_session_id_char_a_id_char_b_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_relationships
    ADD CONSTRAINT character_relationships_session_id_char_a_id_char_b_id_key UNIQUE (session_id, char_a_id, char_b_id);


--
-- Name: character_species character_species_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_species
    ADD CONSTRAINT character_species_pkey PRIMARY KEY (character_id, species_id);


--
-- Name: character_traits character_traits_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_traits
    ADD CONSTRAINT character_traits_pkey PRIMARY KEY (id);


--
-- Name: characters characters_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.characters
    ADD CONSTRAINT characters_pkey PRIMARY KEY (id);


--
-- Name: chekhov_elements chekhov_elements_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.chekhov_elements
    ADD CONSTRAINT chekhov_elements_pkey PRIMARY KEY (id);


--
-- Name: choices choices_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.choices
    ADD CONSTRAINT choices_pkey PRIMARY KEY (id);


--
-- Name: clues clues_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.clues
    ADD CONSTRAINT clues_pkey PRIMARY KEY (id);


--
-- Name: colonies colonies_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.colonies
    ADD CONSTRAINT colonies_pkey PRIMARY KEY (id);


--
-- Name: colonization_projects colonization_projects_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.colonization_projects
    ADD CONSTRAINT colonization_projects_pkey PRIMARY KEY (id);


--
-- Name: combat_results combat_results_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_results
    ADD CONSTRAINT combat_results_pkey PRIMARY KEY (id);


--
-- Name: combat_rounds combat_rounds_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_rounds
    ADD CONSTRAINT combat_rounds_pkey PRIMARY KEY (id);


--
-- Name: combat_stats combat_stats_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_stats
    ADD CONSTRAINT combat_stats_pkey PRIMARY KEY (id);


--
-- Name: combat_stats combat_stats_ship_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_stats
    ADD CONSTRAINT combat_stats_ship_id_key UNIQUE (ship_id);


--
-- Name: commodities commodities_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.commodities
    ADD CONSTRAINT commodities_pkey PRIMARY KEY (id);


--
-- Name: commodities commodities_session_id_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.commodities
    ADD CONSTRAINT commodities_session_id_name_key UNIQUE (session_id, name);


--
-- Name: complaint_boxes complaint_boxes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.complaint_boxes
    ADD CONSTRAINT complaint_boxes_pkey PRIMARY KEY (id);


--
-- Name: complaints complaints_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.complaints
    ADD CONSTRAINT complaints_pkey PRIMARY KEY (id);


--
-- Name: consequence_seeds consequence_seeds_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.consequence_seeds
    ADD CONSTRAINT consequence_seeds_pkey PRIMARY KEY (id);


--
-- Name: containment_measures containment_measures_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.containment_measures
    ADD CONSTRAINT containment_measures_name_key UNIQUE (name);


--
-- Name: containment_measures containment_measures_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.containment_measures
    ADD CONSTRAINT containment_measures_pkey PRIMARY KEY (id);


--
-- Name: conversation_log conversation_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.conversation_log
    ADD CONSTRAINT conversation_log_pkey PRIMARY KEY (id);


--
-- Name: corporate_assets corporate_assets_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporate_assets
    ADD CONSTRAINT corporate_assets_pkey PRIMARY KEY (id);


--
-- Name: corporate_contracts corporate_contracts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporate_contracts
    ADD CONSTRAINT corporate_contracts_pkey PRIMARY KEY (id);


--
-- Name: corporations corporations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporations
    ADD CONSTRAINT corporations_pkey PRIMARY KEY (id);


--
-- Name: corporations corporations_session_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporations
    ADD CONSTRAINT corporations_session_name_key UNIQUE (session_id, name);


--
-- Name: counter_intel_ops counter_intel_ops_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.counter_intel_ops
    ADD CONSTRAINT counter_intel_ops_pkey PRIMARY KEY (id);


--
-- Name: crew_allocation_log crew_allocation_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_allocation_log
    ADD CONSTRAINT crew_allocation_log_pkey PRIMARY KEY (id);


--
-- Name: crew_consumption_log crew_consumption_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_consumption_log
    ADD CONSTRAINT crew_consumption_log_pkey PRIMARY KEY (id);


--
-- Name: crew_factions crew_factions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_factions
    ADD CONSTRAINT crew_factions_pkey PRIMARY KEY (id);


--
-- Name: crew_production_log crew_production_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_production_log
    ADD CONSTRAINT crew_production_log_pkey PRIMARY KEY (id);


--
-- Name: crew_roster crew_roster_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_roster
    ADD CONSTRAINT crew_roster_pkey PRIMARY KEY (id);


--
-- Name: crew_skills crew_skills_crew_id_skill_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_skills
    ADD CONSTRAINT crew_skills_crew_id_skill_name_key UNIQUE (crew_id, skill_name);


--
-- Name: crew_skills crew_skills_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_skills
    ADD CONSTRAINT crew_skills_pkey PRIMARY KEY (id);


--
-- Name: crew_xp_log crew_xp_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_xp_log
    ADD CONSTRAINT crew_xp_log_pkey PRIMARY KEY (id);


--
-- Name: crisis_events crisis_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crisis_events
    ADD CONSTRAINT crisis_events_pkey PRIMARY KEY (id);


--
-- Name: damage_resistances damage_resistances_entity_type_entity_id_resistance_type_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.damage_resistances
    ADD CONSTRAINT damage_resistances_entity_type_entity_id_resistance_type_key UNIQUE (entity_type, entity_id, resistance_type);


--
-- Name: damage_resistances damage_resistances_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.damage_resistances
    ADD CONSTRAINT damage_resistances_pkey PRIMARY KEY (id);


--
-- Name: dark_ops dark_ops_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.dark_ops
    ADD CONSTRAINT dark_ops_pkey PRIMARY KEY (id);


--
-- Name: defense_installations defense_installations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.defense_installations
    ADD CONSTRAINT defense_installations_pkey PRIMARY KEY (id);


--
-- Name: difficulty_tiers difficulty_tiers_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.difficulty_tiers
    ADD CONSTRAINT difficulty_tiers_pkey PRIMARY KEY (id);


--
-- Name: difficulty_tiers difficulty_tiers_tier_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.difficulty_tiers
    ADD CONSTRAINT difficulty_tiers_tier_name_key UNIQUE (tier_name);


--
-- Name: dig_sites dig_sites_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.dig_sites
    ADD CONSTRAINT dig_sites_pkey PRIMARY KEY (id);


--
-- Name: dig_sites dig_sites_session_id_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.dig_sites
    ADD CONSTRAINT dig_sites_session_id_name_key UNIQUE (session_id, name);


--
-- Name: diplomatic_actions diplomatic_actions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.diplomatic_actions
    ADD CONSTRAINT diplomatic_actions_pkey PRIMARY KEY (id);


--
-- Name: disaster_templates disaster_templates_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.disaster_templates
    ADD CONSTRAINT disaster_templates_name_key UNIQUE (name);


--
-- Name: disaster_templates disaster_templates_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.disaster_templates
    ADD CONSTRAINT disaster_templates_pkey PRIMARY KEY (id);


--
-- Name: discoveries discoveries_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.discoveries
    ADD CONSTRAINT discoveries_pkey PRIMARY KEY (id);


--
-- Name: duels duels_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.duels
    ADD CONSTRAINT duels_pkey PRIMARY KEY (id);


--
-- Name: economic_crises economic_crises_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.economic_crises
    ADD CONSTRAINT economic_crises_pkey PRIMARY KEY (id);


--
-- Name: economic_tracker economic_tracker_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.economic_tracker
    ADD CONSTRAINT economic_tracker_pkey PRIMARY KEY (id);


--
-- Name: enrolled_crew enrolled_crew_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.enrolled_crew
    ADD CONSTRAINT enrolled_crew_pkey PRIMARY KEY (id);


--
-- Name: envoys envoys_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.envoys
    ADD CONSTRAINT envoys_pkey PRIMARY KEY (id);


--
-- Name: eradication_campaigns eradication_campaigns_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.eradication_campaigns
    ADD CONSTRAINT eradication_campaigns_pkey PRIMARY KEY (id);


--
-- Name: escape_countermeasures escape_countermeasures_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.escape_countermeasures
    ADD CONSTRAINT escape_countermeasures_pkey PRIMARY KEY (id);


--
-- Name: espionage_missions espionage_missions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.espionage_missions
    ADD CONSTRAINT espionage_missions_pkey PRIMARY KEY (id);


--
-- Name: espionage_operations espionage_operations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.espionage_operations
    ADD CONSTRAINT espionage_operations_pkey PRIMARY KEY (id);


--
-- Name: event_templates event_templates_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.event_templates
    ADD CONSTRAINT event_templates_pkey PRIMARY KEY (id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: faction_ai_state faction_ai_state_faction_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_ai_state
    ADD CONSTRAINT faction_ai_state_faction_name_key UNIQUE (faction_name);


--
-- Name: faction_ai_state faction_ai_state_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_ai_state
    ADD CONSTRAINT faction_ai_state_pkey PRIMARY KEY (id);


--
-- Name: faction_policies faction_policies_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_policies
    ADD CONSTRAINT faction_policies_pkey PRIMARY KEY (id);


--
-- Name: faction_relations faction_relations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_relations
    ADD CONSTRAINT faction_relations_pkey PRIMARY KEY (id);


--
-- Name: faction_relations faction_relations_session_id_faction_a_faction_b_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_relations
    ADD CONSTRAINT faction_relations_session_id_faction_a_faction_b_key UNIQUE (session_id, faction_a, faction_b);


--
-- Name: faction_ships faction_ships_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_ships
    ADD CONSTRAINT faction_ships_pkey PRIMARY KEY (id);


--
-- Name: faction_slave_policy faction_slave_policy_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_slave_policy
    ADD CONSTRAINT faction_slave_policy_pkey PRIMARY KEY (id);


--
-- Name: faction_species_rights faction_species_rights_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_species_rights
    ADD CONSTRAINT faction_species_rights_pkey PRIMARY KEY (id);


--
-- Name: faction_trade_deals faction_trade_deals_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_trade_deals
    ADD CONSTRAINT faction_trade_deals_pkey PRIMARY KEY (id);


--
-- Name: factions factions_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.factions
    ADD CONSTRAINT factions_name_key UNIQUE (name);


--
-- Name: factions factions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.factions
    ADD CONSTRAINT factions_pkey PRIMARY KEY (id);


--
-- Name: family_relations family_relations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.family_relations
    ADD CONSTRAINT family_relations_pkey PRIMARY KEY (id);


--
-- Name: family_relations family_relations_session_id_member_id_relation_type_related_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.family_relations
    ADD CONSTRAINT family_relations_session_id_member_id_relation_type_related_key UNIQUE (session_id, member_id, relation_type, related_id);


--
-- Name: fleet_formations fleet_formations_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleet_formations
    ADD CONSTRAINT fleet_formations_name_key UNIQUE (name);


--
-- Name: fleet_formations fleet_formations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleet_formations
    ADD CONSTRAINT fleet_formations_pkey PRIMARY KEY (id);


--
-- Name: fleet_members fleet_members_fleet_id_ship_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleet_members
    ADD CONSTRAINT fleet_members_fleet_id_ship_id_key UNIQUE (fleet_id, ship_id);


--
-- Name: fleet_members fleet_members_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleet_members
    ADD CONSTRAINT fleet_members_pkey PRIMARY KEY (id);


--
-- Name: fleets fleets_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleets
    ADD CONSTRAINT fleets_pkey PRIMARY KEY (id);


--
-- Name: global_modifiers global_modifiers_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.global_modifiers
    ADD CONSTRAINT global_modifiers_pkey PRIMARY KEY (id);


--
-- Name: global_settings global_settings_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.global_settings
    ADD CONSTRAINT global_settings_pkey PRIMARY KEY (key);


--
-- Name: governance_projects governance_projects_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.governance_projects
    ADD CONSTRAINT governance_projects_pkey PRIMARY KEY (id);


--
-- Name: governor_applicants governor_applicants_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.governor_applicants
    ADD CONSTRAINT governor_applicants_pkey PRIMARY KEY (id);


--
-- Name: grand_plan grand_plan_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.grand_plan
    ADD CONSTRAINT grand_plan_pkey PRIMARY KEY (id);


--
-- Name: grand_plan grand_plan_session_id_item_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.grand_plan
    ADD CONSTRAINT grand_plan_session_id_item_name_key UNIQUE (session_id, item_name);


--
-- Name: guardrail_log guardrail_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.guardrail_log
    ADD CONSTRAINT guardrail_log_pkey PRIMARY KEY (id);


--
-- Name: horror_events horror_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.horror_events
    ADD CONSTRAINT horror_events_pkey PRIMARY KEY (id);


--
-- Name: ideology_state ideology_state_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ideology_state
    ADD CONSTRAINT ideology_state_pkey PRIMARY KEY (session_id);


--
-- Name: image_generations image_generations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.image_generations
    ADD CONSTRAINT image_generations_pkey PRIMARY KEY (id);


--
-- Name: image_prompts image_prompts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.image_prompts
    ADD CONSTRAINT image_prompts_pkey PRIMARY KEY (id);


--
-- Name: incoming_raids incoming_raids_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.incoming_raids
    ADD CONSTRAINT incoming_raids_pkey PRIMARY KEY (id);


--
-- Name: infestation_instances infestation_instances_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_instances
    ADD CONSTRAINT infestation_instances_pkey PRIMARY KEY (id);


--
-- Name: infestation_stages infestation_stages_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_stages
    ADD CONSTRAINT infestation_stages_name_key UNIQUE (name);


--
-- Name: infestation_stages infestation_stages_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_stages
    ADD CONSTRAINT infestation_stages_pkey PRIMARY KEY (id);


--
-- Name: infrastructure_instances infrastructure_instances_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_instances
    ADD CONSTRAINT infrastructure_instances_pkey PRIMARY KEY (id);


--
-- Name: infrastructure_production infrastructure_production_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_production
    ADD CONSTRAINT infrastructure_production_pkey PRIMARY KEY (id);


--
-- Name: infrastructure_types infrastructure_types_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_types
    ADD CONSTRAINT infrastructure_types_name_key UNIQUE (name);


--
-- Name: infrastructure_types infrastructure_types_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_types
    ADD CONSTRAINT infrastructure_types_pkey PRIMARY KEY (id);


--
-- Name: intel_reports intel_reports_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.intel_reports
    ADD CONSTRAINT intel_reports_pkey PRIMARY KEY (id);


--
-- Name: interrogation_log interrogation_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.interrogation_log
    ADD CONSTRAINT interrogation_log_pkey PRIMARY KEY (id);


--
-- Name: intimacy_events intimacy_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.intimacy_events
    ADD CONSTRAINT intimacy_events_pkey PRIMARY KEY (id);


--
-- Name: investigation_log investigation_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.investigation_log
    ADD CONSTRAINT investigation_log_pkey PRIMARY KEY (id);


--
-- Name: investigations investigations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.investigations
    ADD CONSTRAINT investigations_pkey PRIMARY KEY (id);


--
-- Name: jealousy_states jealousy_states_character_id_rival_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.jealousy_states
    ADD CONSTRAINT jealousy_states_character_id_rival_id_key UNIQUE (character_id, rival_id);


--
-- Name: jealousy_states jealousy_states_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.jealousy_states
    ADD CONSTRAINT jealousy_states_pkey PRIMARY KEY (id);


--
-- Name: leader_events leader_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.leader_events
    ADD CONSTRAINT leader_events_pkey PRIMARY KEY (id);


--
-- Name: leaders leaders_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.leaders
    ADD CONSTRAINT leaders_pkey PRIMARY KEY (id);


--
-- Name: legendary_artifacts legendary_artifacts_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.legendary_artifacts
    ADD CONSTRAINT legendary_artifacts_name_key UNIQUE (name);


--
-- Name: legendary_artifacts legendary_artifacts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.legendary_artifacts
    ADD CONSTRAINT legendary_artifacts_pkey PRIMARY KEY (id);


--
-- Name: legio_structure legio_structure_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.legio_structure
    ADD CONSTRAINT legio_structure_pkey PRIMARY KEY (id);


--
-- Name: legio_structure legio_structure_session_id_legio_id_century_num_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.legio_structure
    ADD CONSTRAINT legio_structure_session_id_legio_id_century_num_key UNIQUE (session_id, legio_id, century_num);


--
-- Name: location_catalog location_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.location_catalog
    ADD CONSTRAINT location_catalog_pkey PRIMARY KEY (name);


--
-- Name: locations locations_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.locations
    ADD CONSTRAINT locations_pkey PRIMARY KEY (id);


--
-- Name: material_stockpiles material_stockpiles_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.material_stockpiles
    ADD CONSTRAINT material_stockpiles_pkey PRIMARY KEY (id);


--
-- Name: materials materials_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.materials
    ADD CONSTRAINT materials_name_key UNIQUE (name);


--
-- Name: materials materials_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.materials
    ADD CONSTRAINT materials_pkey PRIMARY KEY (id);


--
-- Name: megastructure_construction megastructure_construction_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_construction
    ADD CONSTRAINT megastructure_construction_pkey PRIMARY KEY (id);


--
-- Name: megastructure_types megastructure_types_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_types
    ADD CONSTRAINT megastructure_types_name_key UNIQUE (name);


--
-- Name: megastructure_types megastructure_types_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_types
    ADD CONSTRAINT megastructure_types_pkey PRIMARY KEY (id);


--
-- Name: migration_hashes migration_hashes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.migration_hashes
    ADD CONSTRAINT migration_hashes_pkey PRIMARY KEY (filename);


--
-- Name: migration_versions migration_versions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.migration_versions
    ADD CONSTRAINT migration_versions_pkey PRIMARY KEY (id);


--
-- Name: migration_versions migration_versions_version_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.migration_versions
    ADD CONSTRAINT migration_versions_version_key UNIQUE (version);


--
-- Name: military_expenditure military_expenditure_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.military_expenditure
    ADD CONSTRAINT military_expenditure_pkey PRIMARY KEY (id);


--
-- Name: modules modules_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.modules
    ADD CONSTRAINT modules_pkey PRIMARY KEY (id);


--
-- Name: morale_history morale_history_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.morale_history
    ADD CONSTRAINT morale_history_pkey PRIMARY KEY (id);


--
-- Name: morality_log morality_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.morality_log
    ADD CONSTRAINT morality_log_pkey PRIMARY KEY (id);


--
-- Name: mystery_templates mystery_templates_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.mystery_templates
    ADD CONSTRAINT mystery_templates_name_key UNIQUE (name);


--
-- Name: mystery_templates mystery_templates_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.mystery_templates
    ADD CONSTRAINT mystery_templates_pkey PRIMARY KEY (id);


--
-- Name: narrative_hooks narrative_hooks_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrative_hooks
    ADD CONSTRAINT narrative_hooks_pkey PRIMARY KEY (id);


--
-- Name: narrative_pacing narrative_pacing_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrative_pacing
    ADD CONSTRAINT narrative_pacing_pkey PRIMARY KEY (session_id);


--
-- Name: narrative_seeds narrative_seeds_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrative_seeds
    ADD CONSTRAINT narrative_seeds_pkey PRIMARY KEY (id);


--
-- Name: narrator_cost_log narrator_cost_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrator_cost_log
    ADD CONSTRAINT narrator_cost_log_pkey PRIMARY KEY (id);


--
-- Name: news_articles news_articles_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.news_articles
    ADD CONSTRAINT news_articles_pkey PRIMARY KEY (id);


--
-- Name: novel_chunks novel_chunks_book_chunk_index_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.novel_chunks
    ADD CONSTRAINT novel_chunks_book_chunk_index_key UNIQUE (book, chunk_index);


--
-- Name: novel_chunks novel_chunks_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.novel_chunks
    ADD CONSTRAINT novel_chunks_pkey PRIMARY KEY (id);


--
-- Name: npc_internal_state npc_internal_state_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.npc_internal_state
    ADD CONSTRAINT npc_internal_state_pkey PRIMARY KEY (character_id, session_id);


--
-- Name: npc_offscreen_interactions npc_offscreen_interactions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.npc_offscreen_interactions
    ADD CONSTRAINT npc_offscreen_interactions_pkey PRIMARY KEY (id);


--
-- Name: objectives objectives_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.objectives
    ADD CONSTRAINT objectives_pkey PRIMARY KEY (id);


--
-- Name: pirate_activities pirate_activities_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_activities
    ADD CONSTRAINT pirate_activities_pkey PRIMARY KEY (id);


--
-- Name: pirate_alerts pirate_alerts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_alerts
    ADD CONSTRAINT pirate_alerts_pkey PRIMARY KEY (id);


--
-- Name: pirate_artifacts pirate_artifacts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_artifacts
    ADD CONSTRAINT pirate_artifacts_pkey PRIMARY KEY (id);


--
-- Name: pirate_bases pirate_bases_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_bases
    ADD CONSTRAINT pirate_bases_pkey PRIMARY KEY (id);


--
-- Name: pirate_bounties pirate_bounties_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_bounties
    ADD CONSTRAINT pirate_bounties_pkey PRIMARY KEY (id);


--
-- Name: pirate_extortion pirate_extortion_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_extortion
    ADD CONSTRAINT pirate_extortion_pkey PRIMARY KEY (id);


--
-- Name: pirate_fleet_templates pirate_fleet_templates_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_fleet_templates
    ADD CONSTRAINT pirate_fleet_templates_pkey PRIMARY KEY (id);


--
-- Name: pirate_loot_tables pirate_loot_tables_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_loot_tables
    ADD CONSTRAINT pirate_loot_tables_pkey PRIMARY KEY (id);


--
-- Name: pirate_raids pirate_raids_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_raids
    ADD CONSTRAINT pirate_raids_pkey PRIMARY KEY (id);


--
-- Name: pirate_salvage_templates pirate_salvage_templates_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_salvage_templates
    ADD CONSTRAINT pirate_salvage_templates_pkey PRIMARY KEY (id);


--
-- Name: pirate_ship_classes pirate_ship_classes_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_ship_classes
    ADD CONSTRAINT pirate_ship_classes_name_key UNIQUE (name);


--
-- Name: pirate_ship_classes pirate_ship_classes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_ship_classes
    ADD CONSTRAINT pirate_ship_classes_pkey PRIMARY KEY (id);


--
-- Name: pirate_zones pirate_zones_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_zones
    ADD CONSTRAINT pirate_zones_pkey PRIMARY KEY (id);


--
-- Name: planet_features planet_features_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_features
    ADD CONSTRAINT planet_features_pkey PRIMARY KEY (id);


--
-- Name: planet_population planet_population_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_population
    ADD CONSTRAINT planet_population_pkey PRIMARY KEY (id);


--
-- Name: planet_population planet_population_session_id_planet_id_species_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_population
    ADD CONSTRAINT planet_population_session_id_planet_id_species_id_key UNIQUE (session_id, planet_id, species_id);


--
-- Name: planet_types_catalog planet_types_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_types_catalog
    ADD CONSTRAINT planet_types_catalog_pkey PRIMARY KEY (name);


--
-- Name: planets planets_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planets
    ADD CONSTRAINT planets_pkey PRIMARY KEY (id);


--
-- Name: player_action_catalog player_action_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_action_catalog
    ADD CONSTRAINT player_action_catalog_pkey PRIMARY KEY (id);


--
-- Name: player_action_log player_action_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_action_log
    ADD CONSTRAINT player_action_log_pkey PRIMARY KEY (id);


--
-- Name: player_context player_context_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_context
    ADD CONSTRAINT player_context_pkey PRIMARY KEY (session_id);


--
-- Name: player_trades player_trades_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_trades
    ADD CONSTRAINT player_trades_pkey PRIMARY KEY (id);


--
-- Name: policy_catalog policy_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.policy_catalog
    ADD CONSTRAINT policy_catalog_pkey PRIMARY KEY (id);


--
-- Name: policy_registry policy_registry_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.policy_registry
    ADD CONSTRAINT policy_registry_pkey PRIMARY KEY (id);


--
-- Name: political_factions political_factions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.political_factions
    ADD CONSTRAINT political_factions_pkey PRIMARY KEY (id);


--
-- Name: population_sentiment population_sentiment_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.population_sentiment
    ADD CONSTRAINT population_sentiment_pkey PRIMARY KEY (id);


--
-- Name: population_sentiment population_sentiment_session_id_territory_id_faction_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.population_sentiment
    ADD CONSTRAINT population_sentiment_session_id_territory_id_faction_id_key UNIQUE (session_id, territory_id, faction_id);


--
-- Name: port_types port_types_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.port_types
    ADD CONSTRAINT port_types_name_key UNIQUE (name);


--
-- Name: port_types port_types_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.port_types
    ADD CONSTRAINT port_types_pkey PRIMARY KEY (id);


--
-- Name: port_upgrades port_upgrades_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.port_upgrades
    ADD CONSTRAINT port_upgrades_pkey PRIMARY KEY (id);


--
-- Name: ports ports_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ports
    ADD CONSTRAINT ports_pkey PRIMARY KEY (id);


--
-- Name: pregnancies pregnancies_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pregnancies
    ADD CONSTRAINT pregnancies_pkey PRIMARY KEY (id);


--
-- Name: pregnancies pregnancies_session_id_mother_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pregnancies
    ADD CONSTRAINT pregnancies_session_id_mother_id_key UNIQUE (session_id, mother_id);


--
-- Name: price_history price_history_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.price_history
    ADD CONSTRAINT price_history_pkey PRIMARY KEY (id);


--
-- Name: prisoner_intel_pipeline prisoner_intel_pipeline_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.prisoner_intel_pipeline
    ADD CONSTRAINT prisoner_intel_pipeline_pkey PRIMARY KEY (id);


--
-- Name: prisoners prisoners_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.prisoners
    ADD CONSTRAINT prisoners_pkey PRIMARY KEY (id);


--
-- Name: production_consumption_log production_consumption_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_consumption_log
    ADD CONSTRAINT production_consumption_log_pkey PRIMARY KEY (id);


--
-- Name: production_lines production_lines_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_lines
    ADD CONSTRAINT production_lines_pkey PRIMARY KEY (id);


--
-- Name: production_queue production_queue_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_queue
    ADD CONSTRAINT production_queue_pkey PRIMARY KEY (id);


--
-- Name: production_requirements production_requirements_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_requirements
    ADD CONSTRAINT production_requirements_pkey PRIMARY KEY (id);


--
-- Name: propaganda_campaigns propaganda_campaigns_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.propaganda_campaigns
    ADD CONSTRAINT propaganda_campaigns_pkey PRIMARY KEY (id);


--
-- Name: public_opinion public_opinion_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.public_opinion
    ADD CONSTRAINT public_opinion_pkey PRIMARY KEY (id);


--
-- Name: public_opinion public_opinion_session_id_faction_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.public_opinion
    ADD CONSTRAINT public_opinion_session_id_faction_name_key UNIQUE (session_id, faction_name);


--
-- Name: quarterly_tasks quarterly_tasks_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.quarterly_tasks
    ADD CONSTRAINT quarterly_tasks_pkey PRIMARY KEY (id);


--
-- Name: quests quests_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.quests
    ADD CONSTRAINT quests_pkey PRIMARY KEY (id);


--
-- Name: raid_log raid_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.raid_log
    ADD CONSTRAINT raid_log_pkey PRIMARY KEY (id);


--
-- Name: recipes recipes_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.recipes
    ADD CONSTRAINT recipes_name_key UNIQUE (name);


--
-- Name: recipes recipes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.recipes
    ADD CONSTRAINT recipes_pkey PRIMARY KEY (id);


--
-- Name: refill_log refill_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.refill_log
    ADD CONSTRAINT refill_log_pkey PRIMARY KEY (id);


--
-- Name: reputation_events reputation_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.reputation_events
    ADD CONSTRAINT reputation_events_pkey PRIMARY KEY (id);


--
-- Name: research_labs research_labs_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.research_labs
    ADD CONSTRAINT research_labs_pkey PRIMARY KEY (id);


--
-- Name: research_projects research_projects_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.research_projects
    ADD CONSTRAINT research_projects_pkey PRIMARY KEY (id);


--
-- Name: research_queue research_queue_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.research_queue
    ADD CONSTRAINT research_queue_pkey PRIMARY KEY (id);


--
-- Name: resource_inventory resource_inventory_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.resource_inventory
    ADD CONSTRAINT resource_inventory_pkey PRIMARY KEY (resource_id);


--
-- Name: resource_production resource_production_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.resource_production
    ADD CONSTRAINT resource_production_pkey PRIMARY KEY (source);


--
-- Name: resources resources_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.resources
    ADD CONSTRAINT resources_pkey PRIMARY KEY (session_id);


--
-- Name: roll_history roll_history_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_history
    ADD CONSTRAINT roll_history_pkey PRIMARY KEY (id);


--
-- Name: roll_outcome_tiers roll_outcome_tiers_outcome_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_outcome_tiers
    ADD CONSTRAINT roll_outcome_tiers_outcome_key UNIQUE (outcome);


--
-- Name: roll_outcome_tiers roll_outcome_tiers_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_outcome_tiers
    ADD CONSTRAINT roll_outcome_tiers_pkey PRIMARY KEY (id);


--
-- Name: roll_state roll_state_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_state
    ADD CONSTRAINT roll_state_pkey PRIMARY KEY (session_id);


--
-- Name: roll_types roll_types_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_types
    ADD CONSTRAINT roll_types_pkey PRIMARY KEY (id);


--
-- Name: roll_types roll_types_roll_code_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_types
    ADD CONSTRAINT roll_types_roll_code_key UNIQUE (roll_code);


--
-- Name: romance_arcs romance_arcs_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.romance_arcs
    ADD CONSTRAINT romance_arcs_pkey PRIMARY KEY (id);


--
-- Name: romance_arcs romance_arcs_session_id_character_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.romance_arcs
    ADD CONSTRAINT romance_arcs_session_id_character_id_key UNIQUE (session_id, character_id);


--
-- Name: romance_tiers romance_tiers_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.romance_tiers
    ADD CONSTRAINT romance_tiers_pkey PRIMARY KEY (id);


--
-- Name: romance_tiers romance_tiers_tier_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.romance_tiers
    ADD CONSTRAINT romance_tiers_tier_name_key UNIQUE (tier_name);


--
-- Name: royal_accounts royal_accounts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.royal_accounts
    ADD CONSTRAINT royal_accounts_pkey PRIMARY KEY (id);


--
-- Name: royal_accounts royal_accounts_session_id_account_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.royal_accounts
    ADD CONSTRAINT royal_accounts_session_id_account_name_key UNIQUE (session_id, account_name);


--
-- Name: royal_offspring royal_offspring_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.royal_offspring
    ADD CONSTRAINT royal_offspring_pkey PRIMARY KEY (id);


--
-- Name: savepoints savepoints_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.savepoints
    ADD CONSTRAINT savepoints_pkey PRIMARY KEY (id);


--
-- Name: scene_stack scene_stack_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scene_stack
    ADD CONSTRAINT scene_stack_pkey PRIMARY KEY (id);


--
-- Name: science_missions science_missions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.science_missions
    ADD CONSTRAINT science_missions_pkey PRIMARY KEY (id);


--
-- Name: scientific_theories scientific_theories_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scientific_theories
    ADD CONSTRAINT scientific_theories_pkey PRIMARY KEY (id);


--
-- Name: scientist_assignments scientist_assignments_character_id_lab_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scientist_assignments
    ADD CONSTRAINT scientist_assignments_character_id_lab_id_key UNIQUE (character_id, lab_id);


--
-- Name: scientist_assignments scientist_assignments_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scientist_assignments
    ADD CONSTRAINT scientist_assignments_pkey PRIMARY KEY (id);


--
-- Name: score_history score_history_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.score_history
    ADD CONSTRAINT score_history_pkey PRIMARY KEY (id);


--
-- Name: secrets secrets_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.secrets
    ADD CONSTRAINT secrets_pkey PRIMARY KEY (id);


--
-- Name: sector_connections sector_connections_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_connections
    ADD CONSTRAINT sector_connections_pkey PRIMARY KEY (id);


--
-- Name: sector_connections sector_connections_session_id_from_sector_id_to_sector_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_connections
    ADD CONSTRAINT sector_connections_session_id_from_sector_id_to_sector_id_key UNIQUE (session_id, from_sector_id, to_sector_id);


--
-- Name: sector_resources sector_resources_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_resources
    ADD CONSTRAINT sector_resources_pkey PRIMARY KEY (id);


--
-- Name: sector_visibility sector_visibility_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_visibility
    ADD CONSTRAINT sector_visibility_pkey PRIMARY KEY (id);


--
-- Name: sector_visibility sector_visibility_session_id_sector_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_visibility
    ADD CONSTRAINT sector_visibility_session_id_sector_id_key UNIQUE (session_id, sector_id);


--
-- Name: sectors sectors_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sectors
    ADD CONSTRAINT sectors_pkey PRIMARY KEY (id);


--
-- Name: sectors sectors_session_id_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sectors
    ADD CONSTRAINT sectors_session_id_name_key UNIQUE (session_id, name);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: ship_armaments ship_armaments_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_armaments
    ADD CONSTRAINT ship_armaments_pkey PRIMARY KEY (id);


--
-- Name: ship_classes ship_classes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_classes
    ADD CONSTRAINT ship_classes_pkey PRIMARY KEY (id);


--
-- Name: ship_modules ship_modules_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_modules
    ADD CONSTRAINT ship_modules_pkey PRIMARY KEY (id);


--
-- Name: ship_roles ship_roles_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_roles
    ADD CONSTRAINT ship_roles_name_key UNIQUE (name);


--
-- Name: ship_roles ship_roles_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_roles
    ADD CONSTRAINT ship_roles_pkey PRIMARY KEY (id);


--
-- Name: ship_sub_classes ship_sub_classes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_sub_classes
    ADD CONSTRAINT ship_sub_classes_pkey PRIMARY KEY (id);


--
-- Name: ship_sub_classes ship_sub_classes_ship_type_sub_class_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_sub_classes
    ADD CONSTRAINT ship_sub_classes_ship_type_sub_class_key UNIQUE (ship_type, sub_class);


--
-- Name: ship_tech_bonuses ship_tech_bonuses_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_tech_bonuses
    ADD CONSTRAINT ship_tech_bonuses_pkey PRIMARY KEY (id);


--
-- Name: ship_types ship_types_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_types
    ADD CONSTRAINT ship_types_pkey PRIMARY KEY (code);


--
-- Name: ships ships_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ships
    ADD CONSTRAINT ships_pkey PRIMARY KEY (id);


--
-- Name: sieges sieges_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sieges
    ADD CONSTRAINT sieges_pkey PRIMARY KEY (id);


--
-- Name: slave_births slave_births_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_births
    ADD CONSTRAINT slave_births_pkey PRIMARY KEY (id);


--
-- Name: slave_market slave_market_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_market
    ADD CONSTRAINT slave_market_pkey PRIMARY KEY (id);


--
-- Name: slave_revolts slave_revolts_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_revolts
    ADD CONSTRAINT slave_revolts_pkey PRIMARY KEY (id);


--
-- Name: slave_training slave_training_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_training
    ADD CONSTRAINT slave_training_pkey PRIMARY KEY (id);


--
-- Name: slaves slaves_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slaves
    ADD CONSTRAINT slaves_pkey PRIMARY KEY (id);


--
-- Name: social_events social_events_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.social_events
    ADD CONSTRAINT social_events_pkey PRIMARY KEY (id);


--
-- Name: social_templates social_templates_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.social_templates
    ADD CONSTRAINT social_templates_pkey PRIMARY KEY (id);


--
-- Name: space_animals space_animals_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.space_animals
    ADD CONSTRAINT space_animals_pkey PRIMARY KEY (id);


--
-- Name: space_anomalies space_anomalies_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.space_anomalies
    ADD CONSTRAINT space_anomalies_pkey PRIMARY KEY (id);


--
-- Name: space_lanes space_lanes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.space_lanes
    ADD CONSTRAINT space_lanes_pkey PRIMARY KEY (id);


--
-- Name: species_catalog species_catalog_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.species_catalog
    ADD CONSTRAINT species_catalog_name_key UNIQUE (name);


--
-- Name: species_catalog species_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.species_catalog
    ADD CONSTRAINT species_catalog_pkey PRIMARY KEY (id);


--
-- Name: spy_networks spy_networks_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.spy_networks
    ADD CONSTRAINT spy_networks_pkey PRIMARY KEY (id);


--
-- Name: standing_orders standing_orders_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.standing_orders
    ADD CONSTRAINT standing_orders_pkey PRIMARY KEY (id);


--
-- Name: state state_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.state
    ADD CONSTRAINT state_pkey PRIMARY KEY (session_id);


--
-- Name: state_snapshots state_snapshots_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.state_snapshots
    ADD CONSTRAINT state_snapshots_pkey PRIMARY KEY (id);


--
-- Name: stealth_unit_types stealth_unit_types_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stealth_unit_types
    ADD CONSTRAINT stealth_unit_types_name_key UNIQUE (name);


--
-- Name: stealth_unit_types stealth_unit_types_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stealth_unit_types
    ADD CONSTRAINT stealth_unit_types_pkey PRIMARY KEY (id);


--
-- Name: stealth_units stealth_units_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stealth_units
    ADD CONSTRAINT stealth_units_pkey PRIMARY KEY (id);


--
-- Name: stock_prices stock_prices_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stock_prices
    ADD CONSTRAINT stock_prices_pkey PRIMARY KEY (resource_id);


--
-- Name: story_arcs story_arcs_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_arcs
    ADD CONSTRAINT story_arcs_pkey PRIMARY KEY (id);


--
-- Name: story_checkpoints story_checkpoints_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_checkpoints
    ADD CONSTRAINT story_checkpoints_pkey PRIMARY KEY (id);


--
-- Name: story_log story_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_log
    ADD CONSTRAINT story_log_pkey PRIMARY KEY (id);


--
-- Name: strategic_resources strategic_resources_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.strategic_resources
    ADD CONSTRAINT strategic_resources_name_key UNIQUE (name);


--
-- Name: strategic_resources strategic_resources_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.strategic_resources
    ADD CONSTRAINT strategic_resources_pkey PRIMARY KEY (id);


--
-- Name: stream_templates stream_templates_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stream_templates
    ADD CONSTRAINT stream_templates_pkey PRIMARY KEY (id);


--
-- Name: stream_templates stream_templates_trigger_tag_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stream_templates
    ADD CONSTRAINT stream_templates_trigger_tag_key UNIQUE (trigger_tag);


--
-- Name: supply_depots supply_depots_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.supply_depots
    ADD CONSTRAINT supply_depots_pkey PRIMARY KEY (id);


--
-- Name: supply_lines supply_lines_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.supply_lines
    ADD CONSTRAINT supply_lines_pkey PRIMARY KEY (id);


--
-- Name: tactical_states tactical_states_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tactical_states
    ADD CONSTRAINT tactical_states_pkey PRIMARY KEY (id);


--
-- Name: tactical_states tactical_states_session_id_engagement_id_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tactical_states
    ADD CONSTRAINT tactical_states_session_id_engagement_id_key UNIQUE (session_id, engagement_id);


--
-- Name: tactics_catalog tactics_catalog_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tactics_catalog
    ADD CONSTRAINT tactics_catalog_name_key UNIQUE (name);


--
-- Name: tactics_catalog tactics_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tactics_catalog
    ADD CONSTRAINT tactics_catalog_pkey PRIMARY KEY (id);


--
-- Name: talent_catalog talent_catalog_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.talent_catalog
    ADD CONSTRAINT talent_catalog_name_key UNIQUE (name);


--
-- Name: talent_catalog talent_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.talent_catalog
    ADD CONSTRAINT talent_catalog_pkey PRIMARY KEY (id);


--
-- Name: task_routes task_routes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.task_routes
    ADD CONSTRAINT task_routes_pkey PRIMARY KEY (id);


--
-- Name: tax_history tax_history_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tax_history
    ADD CONSTRAINT tax_history_pkey PRIMARY KEY (id);


--
-- Name: technologies technologies_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.technologies
    ADD CONSTRAINT technologies_pkey PRIMARY KEY (id);


--
-- Name: tension_thresholds tension_thresholds_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tension_thresholds
    ADD CONSTRAINT tension_thresholds_name_key UNIQUE (name);


--
-- Name: tension_thresholds tension_thresholds_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tension_thresholds
    ADD CONSTRAINT tension_thresholds_pkey PRIMARY KEY (id);


--
-- Name: terraforming_projects terraforming_projects_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.terraforming_projects
    ADD CONSTRAINT terraforming_projects_pkey PRIMARY KEY (id);


--
-- Name: territory_modifiers territory_modifiers_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory_modifiers
    ADD CONSTRAINT territory_modifiers_pkey PRIMARY KEY (id);


--
-- Name: territory territory_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory
    ADD CONSTRAINT territory_pkey PRIMARY KEY (id);


--
-- Name: territory_resources territory_resources_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory_resources
    ADD CONSTRAINT territory_resources_pkey PRIMARY KEY (id);


--
-- Name: theme_state theme_state_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.theme_state
    ADD CONSTRAINT theme_state_pkey PRIMARY KEY (session_id);


--
-- Name: tick_summaries tick_summaries_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tick_summaries
    ADD CONSTRAINT tick_summaries_pkey PRIMARY KEY (id);


--
-- Name: time_skip_log time_skip_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.time_skip_log
    ADD CONSTRAINT time_skip_log_pkey PRIMARY KEY (id);


--
-- Name: trade_log trade_log_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trade_log
    ADD CONSTRAINT trade_log_pkey PRIMARY KEY (id);


--
-- Name: trade_routes trade_routes_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trade_routes
    ADD CONSTRAINT trade_routes_pkey PRIMARY KEY (id);


--
-- Name: training_programs training_programs_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.training_programs
    ADD CONSTRAINT training_programs_pkey PRIMARY KEY (id);


--
-- Name: trait_assignments trait_assignments_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trait_assignments
    ADD CONSTRAINT trait_assignments_pkey PRIMARY KEY (assignment_id);


--
-- Name: trait_catalog trait_catalog_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trait_catalog
    ADD CONSTRAINT trait_catalog_pkey PRIMARY KEY (trait_id);


--
-- Name: transport_missions transport_missions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.transport_missions
    ADD CONSTRAINT transport_missions_pkey PRIMARY KEY (id);


--
-- Name: treaties treaties_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.treaties
    ADD CONSTRAINT treaties_pkey PRIMARY KEY (id);


--
-- Name: university_campuses university_campuses_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.university_campuses
    ADD CONSTRAINT university_campuses_pkey PRIMARY KEY (id);


--
-- Name: victory_tracking victory_tracking_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.victory_tracking
    ADD CONSTRAINT victory_tracking_pkey PRIMARY KEY (id);


--
-- Name: voyages voyages_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.voyages
    ADD CONSTRAINT voyages_pkey PRIMARY KEY (id);


--
-- Name: war_exhaustion_effects war_exhaustion_effects_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.war_exhaustion_effects
    ADD CONSTRAINT war_exhaustion_effects_pkey PRIMARY KEY (id);


--
-- Name: wars wars_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.wars
    ADD CONSTRAINT wars_pkey PRIMARY KEY (id);


--
-- Name: weapon_blueprints weapon_blueprints_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapon_blueprints
    ADD CONSTRAINT weapon_blueprints_name_key UNIQUE (name);


--
-- Name: weapon_blueprints weapon_blueprints_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapon_blueprints
    ADD CONSTRAINT weapon_blueprints_pkey PRIMARY KEY (id);


--
-- Name: weapon_kinds weapon_kinds_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapon_kinds
    ADD CONSTRAINT weapon_kinds_pkey PRIMARY KEY (kind);


--
-- Name: weapon_upgrades weapon_upgrades_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapon_upgrades
    ADD CONSTRAINT weapon_upgrades_pkey PRIMARY KEY (id);


--
-- Name: weapons weapons_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapons
    ADD CONSTRAINT weapons_pkey PRIMARY KEY (id);


--
-- Name: wiki_articles wiki_articles_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.wiki_articles
    ADD CONSTRAINT wiki_articles_pkey PRIMARY KEY (id);


--
-- Name: world_reactions world_reactions_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.world_reactions
    ADD CONSTRAINT world_reactions_pkey PRIMARY KEY (id);


--
-- Name: wreck_inventory wreck_inventory_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.wreck_inventory
    ADD CONSTRAINT wreck_inventory_pkey PRIMARY KEY (id);


--
-- Name: yard_capacity yard_capacity_pkey; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.yard_capacity
    ADD CONSTRAINT yard_capacity_pkey PRIMARY KEY (id);


--
-- Name: yard_capacity yard_capacity_yard_name_key; Type: CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.yard_capacity
    ADD CONSTRAINT yard_capacity_yard_name_key UNIQUE (yard_name);


--
-- Name: idx_active_scenes_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_active_scenes_session ON maya_rp.active_scenes USING btree (session_id);


--
-- Name: idx_adjprompt_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_adjprompt_status ON maya_rp.adjutant_prompts USING btree (session_id, status, urgency);


--
-- Name: idx_alerts_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_alerts_session ON maya_rp.alert_queue USING btree (session_id, read, priority DESC);


--
-- Name: idx_animal_encounters_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_animal_encounters_session ON maya_rp.animal_encounters USING btree (session_id);


--
-- Name: idx_animal_encounters_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_animal_encounters_status ON maya_rp.animal_encounters USING btree (status);


--
-- Name: idx_bug_events_infest; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_bug_events_infest ON maya_rp.bug_events USING btree (infestation_id);


--
-- Name: idx_build_queue_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_build_queue_session ON maya_rp.build_queue USING btree (session_id);


--
-- Name: idx_build_queue_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_build_queue_status ON maya_rp.build_queue USING btree (status);


--
-- Name: idx_cabinet_decrees_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_cabinet_decrees_session ON maya_rp.cabinet_decrees USING btree (session_id);


--
-- Name: idx_cabinet_decrees_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_cabinet_decrees_status ON maya_rp.cabinet_decrees USING btree (status);


--
-- Name: idx_cabinet_hierarchy_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_cabinet_hierarchy_session ON maya_rp.cabinet_hierarchy USING btree (session_id);


--
-- Name: idx_cabinet_meetings_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_cabinet_meetings_session ON maya_rp.cabinet_meetings USING btree (session_id);


--
-- Name: idx_chapters_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_chapters_session ON maya_rp.chapters USING btree (session_id);


--
-- Name: idx_char_traits; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_char_traits ON maya_rp.character_traits USING btree (character_id, active);


--
-- Name: idx_characters_clearance; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_characters_clearance ON maya_rp.characters USING btree (clearance_level, screened);


--
-- Name: idx_characters_crew; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_characters_crew ON maya_rp.characters USING btree (crew_id);


--
-- Name: idx_characters_faction; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_characters_faction ON maya_rp.characters USING btree (faction_id);


--
-- Name: idx_characters_species; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_characters_species ON maya_rp.characters USING btree (species_id);


--
-- Name: idx_clues_chain; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_clues_chain ON maya_rp.clues USING btree (connects_to_clue);


--
-- Name: idx_clues_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_clues_session ON maya_rp.clues USING btree (session_id);


--
-- Name: idx_combat_results_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_combat_results_session ON maya_rp.combat_results USING btree (session_id);


--
-- Name: idx_combat_rounds_tactical; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_combat_rounds_tactical ON maya_rp.combat_rounds USING btree (tactical_state_id);


--
-- Name: idx_combat_stats_ship; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_combat_stats_ship ON maya_rp.combat_stats USING btree (ship_id);


--
-- Name: idx_complaints_box; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_complaints_box ON maya_rp.complaints USING btree (box_id);


--
-- Name: idx_convlog_char; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_convlog_char ON maya_rp.conversation_log USING btree (session_id, character_id);


--
-- Name: idx_crew_alloc_log; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_crew_alloc_log ON maya_rp.crew_allocation_log USING btree (session_id);


--
-- Name: idx_crew_cons_log; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_crew_cons_log ON maya_rp.crew_consumption_log USING btree (session_id);


--
-- Name: idx_crew_factions_ship; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_crew_factions_ship ON maya_rp.crew_factions USING btree (ship_id);


--
-- Name: idx_crew_level; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_crew_level ON maya_rp.crew_roster USING btree (level);


--
-- Name: idx_crew_prod_log; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_crew_prod_log ON maya_rp.crew_production_log USING btree (session_id, game_day);


--
-- Name: idx_crew_roster_unassigned; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_crew_roster_unassigned ON maya_rp.crew_roster USING btree (session_id, ship_id, status);


--
-- Name: idx_darkops_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_darkops_session ON maya_rp.dark_ops USING btree (session_id);


--
-- Name: idx_diplomatic_actions_actor; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_diplomatic_actions_actor ON maya_rp.diplomatic_actions USING btree (actor_faction_id);


--
-- Name: idx_discoveries_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_discoveries_session ON maya_rp.discoveries USING btree (session_id);


--
-- Name: idx_discoveries_type; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_discoveries_type ON maya_rp.discoveries USING btree (type);


--
-- Name: idx_duels_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_duels_session ON maya_rp.duels USING btree (session_id, status);


--
-- Name: idx_economic_crises_territory_id; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_economic_crises_territory_id ON maya_rp.economic_crises USING btree (territory_id);


--
-- Name: idx_envoys_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_envoys_status ON maya_rp.envoys USING btree (status);


--
-- Name: idx_erad_campaign_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_erad_campaign_session ON maya_rp.eradication_campaigns USING btree (session_id);


--
-- Name: idx_erad_campaign_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_erad_campaign_status ON maya_rp.eradication_campaigns USING btree (status);


--
-- Name: idx_espionage_faction; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_espionage_faction ON maya_rp.espionage_missions USING btree (faction_id);


--
-- Name: idx_events_session_happened; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_events_session_happened ON maya_rp.events USING btree (session_id, happened_at DESC);


--
-- Name: idx_faction_ships_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_faction_ships_session ON maya_rp.faction_ships USING btree (session_id, faction_name);


--
-- Name: idx_family_father; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_family_father ON maya_rp.characters USING btree (father_id);


--
-- Name: idx_family_member; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_family_member ON maya_rp.family_relations USING btree (member_id);


--
-- Name: idx_family_mother; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_family_mother ON maya_rp.characters USING btree (mother_id);


--
-- Name: idx_family_related; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_family_related ON maya_rp.family_relations USING btree (related_id);


--
-- Name: idx_fleet_members_fleet; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_fleet_members_fleet ON maya_rp.fleet_members USING btree (fleet_id);


--
-- Name: idx_fleets_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_fleets_session ON maya_rp.fleets USING btree (session_id);


--
-- Name: idx_generations_prompt; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_generations_prompt ON maya_rp.image_generations USING btree (prompt_id);


--
-- Name: idx_governance_projects_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_governance_projects_session ON maya_rp.governance_projects USING btree (session_id);


--
-- Name: idx_horror_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_horror_session ON maya_rp.horror_events USING btree (session_id);


--
-- Name: idx_infest_sector; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_infest_sector ON maya_rp.infestation_instances USING btree (sector_id);


--
-- Name: idx_infest_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_infest_session ON maya_rp.infestation_instances USING btree (session_id);


--
-- Name: idx_infest_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_infest_status ON maya_rp.infestation_instances USING btree (status);


--
-- Name: idx_infra_inst_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_infra_inst_session ON maya_rp.infrastructure_instances USING btree (session_id);


--
-- Name: idx_infra_inst_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_infra_inst_status ON maya_rp.infrastructure_instances USING btree (status);


--
-- Name: idx_infra_inst_territory; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_infra_inst_territory ON maya_rp.infrastructure_instances USING btree (territory_id);


--
-- Name: idx_infra_prod_infra; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_infra_prod_infra ON maya_rp.infrastructure_production USING btree (infrastructure_id);


--
-- Name: idx_interrogation_log_prisoner; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_interrogation_log_prisoner ON maya_rp.interrogation_log USING btree (prisoner_id);


--
-- Name: idx_intimacy_char; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_intimacy_char ON maya_rp.intimacy_events USING btree (character_id);


--
-- Name: idx_investigation_log_case; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_investigation_log_case ON maya_rp.investigation_log USING btree (investigation_id);


--
-- Name: idx_investigations_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_investigations_session ON maya_rp.investigations USING btree (session_id);


--
-- Name: idx_lanes_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_lanes_session ON maya_rp.space_lanes USING btree (session_id);


--
-- Name: idx_locations_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_locations_session ON maya_rp.locations USING btree (session_id);


--
-- Name: idx_mega_const_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_mega_const_session ON maya_rp.megastructure_construction USING btree (session_id);


--
-- Name: idx_mega_const_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_mega_const_status ON maya_rp.megastructure_construction USING btree (status);


--
-- Name: idx_morale_history_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_morale_history_session ON maya_rp.morale_history USING btree (session_id);


--
-- Name: idx_morality_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_morality_session ON maya_rp.morality_log USING btree (session_id);


--
-- Name: idx_narrative_hooks_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_narrative_hooks_status ON maya_rp.narrative_hooks USING btree (status);


--
-- Name: idx_narrator_cost; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_narrator_cost ON maya_rp.narrator_cost_log USING btree (session_id, created_at DESC);


--
-- Name: idx_novel_chunks_embedding; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_novel_chunks_embedding ON maya_rp.novel_chunks USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_pal_session_cat; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_pal_session_cat ON maya_rp.player_action_log USING btree (session_id, action_category);


--
-- Name: idx_planet_pop_planet; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_planet_pop_planet ON maya_rp.planet_population USING btree (session_id, planet_id);


--
-- Name: idx_planet_pop_species; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_planet_pop_species ON maya_rp.planet_population USING btree (session_id, species_name);


--
-- Name: idx_planets_type; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_planets_type ON maya_rp.planets USING btree (planet_type);


--
-- Name: idx_pop_sent_fac; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_pop_sent_fac ON maya_rp.population_sentiment USING btree (session_id, faction_id);


--
-- Name: idx_pop_sent_terr; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_pop_sent_terr ON maya_rp.population_sentiment USING btree (session_id, territory_id);


--
-- Name: idx_port_upgrades_port; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_port_upgrades_port ON maya_rp.port_upgrades USING btree (port_id);


--
-- Name: idx_ports_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_ports_session ON maya_rp.ports USING btree (session_id);


--
-- Name: idx_ports_territory; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_ports_territory ON maya_rp.ports USING btree (territory_id);


--
-- Name: idx_prisoners_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_prisoners_session ON maya_rp.prisoners USING btree (session_id);


--
-- Name: idx_prisoners_ship; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_prisoners_ship ON maya_rp.prisoners USING btree (cell_ship_id);


--
-- Name: idx_prisoners_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_prisoners_status ON maya_rp.prisoners USING btree (status);


--
-- Name: idx_production_consumption_log_production; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_production_consumption_log_production ON maya_rp.production_consumption_log USING btree (production_type, production_name);


--
-- Name: idx_prompts_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_prompts_session ON maya_rp.image_prompts USING btree (session_id);


--
-- Name: idx_quarterly_tasks_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_quarterly_tasks_session ON maya_rp.quarterly_tasks USING btree (session_id, status);


--
-- Name: idx_quests_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_quests_session ON maya_rp.quests USING btree (session_id);


--
-- Name: idx_raids_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_raids_session ON maya_rp.incoming_raids USING btree (session_id, ticks_remaining);


--
-- Name: idx_research_projects_field; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_research_projects_field ON maya_rp.research_projects USING btree (field);


--
-- Name: idx_research_projects_field_category; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_research_projects_field_category ON maya_rp.research_projects USING btree (field, category);


--
-- Name: idx_research_queue_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_research_queue_status ON maya_rp.research_queue USING btree (status);


--
-- Name: idx_resource_inventory_resource; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_resource_inventory_resource ON maya_rp.resource_inventory USING btree (resource_id);


--
-- Name: idx_roll_history_code; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_roll_history_code ON maya_rp.roll_history USING btree (roll_code);


--
-- Name: idx_roll_history_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_roll_history_session ON maya_rp.roll_history USING btree (session_id, created_at DESC);


--
-- Name: idx_roll_history_source; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_roll_history_source ON maya_rp.roll_history USING btree (source_table, source_id);


--
-- Name: idx_romance_arcs_character; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_romance_arcs_character ON maya_rp.romance_arcs USING btree (character_id);


--
-- Name: idx_romance_arcs_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_romance_arcs_session ON maya_rp.romance_arcs USING btree (session_id);


--
-- Name: idx_ships_session_status; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_ships_session_status ON maya_rp.ships USING btree (session_id, status);


--
-- Name: idx_sieges_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_sieges_session ON maya_rp.sieges USING btree (session_id);


--
-- Name: idx_social_events_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_social_events_session ON maya_rp.social_events USING btree (session_id);


--
-- Name: idx_social_events_type; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_social_events_type ON maya_rp.social_events USING btree (event_type);


--
-- Name: idx_species_humanlike; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_species_humanlike ON maya_rp.species_catalog USING btree (human_like_pct);


--
-- Name: idx_species_romance; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_species_romance ON maya_rp.species_catalog USING btree (romance_compatible);


--
-- Name: idx_state_snapshots_label; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_state_snapshots_label ON maya_rp.state_snapshots USING btree (session_id, label);


--
-- Name: idx_state_snapshots_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_state_snapshots_session ON maya_rp.state_snapshots USING btree (session_id);


--
-- Name: idx_stealth_units_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_stealth_units_session ON maya_rp.stealth_units USING btree (session_id);


--
-- Name: idx_story_checkpoints_active; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE UNIQUE INDEX idx_story_checkpoints_active ON maya_rp.story_checkpoints USING btree (session_id) WHERE (active = true);


--
-- Name: idx_story_checkpoints_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_story_checkpoints_session ON maya_rp.story_checkpoints USING btree (session_id);


--
-- Name: idx_story_log_happened_at; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_story_log_happened_at ON maya_rp.story_log USING btree (happened_at);


--
-- Name: idx_story_log_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_story_log_session ON maya_rp.story_log USING btree (session_id);


--
-- Name: idx_stream_templates_embed; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_stream_templates_embed ON maya_rp.stream_templates USING hnsw (trigger_tag_embed public.vector_cosine_ops);


--
-- Name: idx_summaries_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_summaries_session ON maya_rp.tick_summaries USING btree (session_id, tick_number DESC);


--
-- Name: idx_tactical_states_engagement; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_tactical_states_engagement ON maya_rp.tactical_states USING btree (session_id, engagement_id);


--
-- Name: idx_tactical_states_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_tactical_states_session ON maya_rp.tactical_states USING btree (session_id);


--
-- Name: idx_tax_history_territory_id; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_tax_history_territory_id ON maya_rp.tax_history USING btree (territory_id);


--
-- Name: idx_territory_controlling_faction; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_territory_controlling_faction ON maya_rp.territory USING btree (controlling_faction);


--
-- Name: idx_territory_faction; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_territory_faction ON maya_rp.territory USING btree (controlling_faction);


--
-- Name: idx_territory_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_territory_session ON maya_rp.territory USING btree (session_id);


--
-- Name: idx_trade_routes_origin; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_trade_routes_origin ON maya_rp.trade_routes USING btree (origin_territory_id);


--
-- Name: idx_treaties_active; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_treaties_active ON maya_rp.treaties USING btree (active);


--
-- Name: idx_treaties_faction_a; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_treaties_faction_a ON maya_rp.treaties USING btree (faction_a_id);


--
-- Name: idx_treaties_faction_b; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_treaties_faction_b ON maya_rp.treaties USING btree (faction_b_id);


--
-- Name: idx_voyages_depart; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_voyages_depart ON maya_rp.voyages USING btree (session_id, depart_day);


--
-- Name: idx_voyages_status_day; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_voyages_status_day ON maya_rp.voyages USING btree (session_id, status, arrive_day);


--
-- Name: idx_voyages_unique; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE UNIQUE INDEX idx_voyages_unique ON maya_rp.voyages USING btree (session_id, voyage_name, depart_day);


--
-- Name: idx_wiki_articles_checkpoint; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_wiki_articles_checkpoint ON maya_rp.wiki_articles USING btree (session_id, checkpoint_id);


--
-- Name: idx_wiki_articles_embedding; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_wiki_articles_embedding ON maya_rp.wiki_articles USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_wiki_articles_session_cat; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_wiki_articles_session_cat ON maya_rp.wiki_articles USING btree (session_id, category);


--
-- Name: idx_wr_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_wr_session ON maya_rp.world_reactions USING btree (session_id, surfaced);


--
-- Name: idx_wreck_inventory_session; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX idx_wreck_inventory_session ON maya_rp.wreck_inventory USING btree (session_id, status);


--
-- Name: news_game_day_idx; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX news_game_day_idx ON maya_rp.news_articles USING btree (session_id, game_day);


--
-- Name: pregnancies_active_idx; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX pregnancies_active_idx ON maya_rp.pregnancies USING btree (session_id, status, due_game_day);


--
-- Name: pregnancies_due_idx; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE INDEX pregnancies_due_idx ON maya_rp.pregnancies USING btree (due_game_day);


--
-- Name: wiki_articles_session_title_key; Type: INDEX; Schema: maya_rp; Owner: -
--

CREATE UNIQUE INDEX wiki_articles_session_title_key ON maya_rp.wiki_articles USING btree (session_id, title);


--
-- Name: active_disasters active_disasters_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_disasters
    ADD CONSTRAINT active_disasters_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: active_disasters active_disasters_template_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_disasters
    ADD CONSTRAINT active_disasters_template_id_fkey FOREIGN KEY (template_id) REFERENCES maya_rp.disaster_templates(id);


--
-- Name: active_events active_events_template_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_events
    ADD CONSTRAINT active_events_template_id_fkey FOREIGN KEY (template_id) REFERENCES maya_rp.event_templates(id) ON DELETE CASCADE;


--
-- Name: active_events active_events_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_events
    ADD CONSTRAINT active_events_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: active_scenes active_scenes_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.active_scenes
    ADD CONSTRAINT active_scenes_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: ai_decision_log ai_decision_log_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_decision_log
    ADD CONSTRAINT ai_decision_log_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: ai_decisions ai_decisions_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_decisions
    ADD CONSTRAINT ai_decisions_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: ai_tactics_history ai_tactics_history_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_tactics_history
    ADD CONSTRAINT ai_tactics_history_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: ai_tactics_history ai_tactics_history_player_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ai_tactics_history
    ADD CONSTRAINT ai_tactics_history_player_faction_id_fkey FOREIGN KEY (player_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: alert_queue alert_queue_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.alert_queue
    ADD CONSTRAINT alert_queue_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: animal_encounters animal_encounters_animal_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.animal_encounters
    ADD CONSTRAINT animal_encounters_animal_id_fkey FOREIGN KEY (animal_id) REFERENCES maya_rp.space_animals(id) ON DELETE CASCADE;


--
-- Name: animal_encounters animal_encounters_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.animal_encounters
    ADD CONSTRAINT animal_encounters_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: animal_encounters animal_encounters_system_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.animal_encounters
    ADD CONSTRAINT animal_encounters_system_id_fkey FOREIGN KEY (system_id) REFERENCES maya_rp.sectors(id) ON DELETE CASCADE;


--
-- Name: anomalies_catalog anomalies_catalog_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.anomalies_catalog
    ADD CONSTRAINT anomalies_catalog_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: anti_cloak_grids anti_cloak_grids_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.anti_cloak_grids
    ADD CONSTRAINT anti_cloak_grids_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: artifact_history artifact_history_artifact_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.artifact_history
    ADD CONSTRAINT artifact_history_artifact_id_fkey FOREIGN KEY (artifact_id) REFERENCES maya_rp.legendary_artifacts(id);


--
-- Name: artifacts artifacts_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.artifacts
    ADD CONSTRAINT artifacts_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: bug_events bug_events_infestation_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_events
    ADD CONSTRAINT bug_events_infestation_id_fkey FOREIGN KEY (infestation_id) REFERENCES maya_rp.infestation_instances(id) ON DELETE CASCADE;


--
-- Name: bug_events bug_events_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_events
    ADD CONSTRAINT bug_events_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: bug_tech_tree bug_tech_tree_prerequisite_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.bug_tech_tree
    ADD CONSTRAINT bug_tech_tree_prerequisite_id_fkey FOREIGN KEY (prerequisite_id) REFERENCES maya_rp.bug_tech_tree(id) ON DELETE SET NULL;


--
-- Name: build_queue build_queue_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.build_queue
    ADD CONSTRAINT build_queue_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: cabinet_decrees cabinet_decrees_delegated_to_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_decrees
    ADD CONSTRAINT cabinet_decrees_delegated_to_fkey FOREIGN KEY (delegated_to) REFERENCES maya_rp.cabinet_hierarchy(id);


--
-- Name: cabinet_decrees cabinet_decrees_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_decrees
    ADD CONSTRAINT cabinet_decrees_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: cabinet_hierarchy cabinet_hierarchy_reports_to_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_hierarchy
    ADD CONSTRAINT cabinet_hierarchy_reports_to_fkey FOREIGN KEY (reports_to) REFERENCES maya_rp.cabinet_hierarchy(id);


--
-- Name: cabinet_hierarchy cabinet_hierarchy_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_hierarchy
    ADD CONSTRAINT cabinet_hierarchy_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: cabinet_meetings cabinet_meetings_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cabinet_meetings
    ADD CONSTRAINT cabinet_meetings_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: cargo cargo_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.cargo
    ADD CONSTRAINT cargo_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: chapters chapters_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.chapters
    ADD CONSTRAINT chapters_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: character_events character_events_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_events
    ADD CONSTRAINT character_events_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: character_events character_events_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_events
    ADD CONSTRAINT character_events_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: character_injuries character_injuries_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_injuries
    ADD CONSTRAINT character_injuries_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: character_injuries character_injuries_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_injuries
    ADD CONSTRAINT character_injuries_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: character_memories character_memories_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_memories
    ADD CONSTRAINT character_memories_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: character_memories character_memories_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_memories
    ADD CONSTRAINT character_memories_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: character_quirks character_quirks_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_quirks
    ADD CONSTRAINT character_quirks_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: character_relationships character_relationships_char_a_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_relationships
    ADD CONSTRAINT character_relationships_char_a_id_fkey FOREIGN KEY (char_a_id) REFERENCES maya_rp.characters(id);


--
-- Name: character_relationships character_relationships_char_b_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_relationships
    ADD CONSTRAINT character_relationships_char_b_id_fkey FOREIGN KEY (char_b_id) REFERENCES maya_rp.characters(id);


--
-- Name: character_relationships character_relationships_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_relationships
    ADD CONSTRAINT character_relationships_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: character_species character_species_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_species
    ADD CONSTRAINT character_species_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: character_species character_species_species_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_species
    ADD CONSTRAINT character_species_species_id_fkey FOREIGN KEY (species_id) REFERENCES maya_rp.species_catalog(id);


--
-- Name: character_traits character_traits_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.character_traits
    ADD CONSTRAINT character_traits_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: characters characters_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.characters
    ADD CONSTRAINT characters_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: chekhov_elements chekhov_elements_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.chekhov_elements
    ADD CONSTRAINT chekhov_elements_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: choices choices_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.choices
    ADD CONSTRAINT choices_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: clues clues_connects_to_clue_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.clues
    ADD CONSTRAINT clues_connects_to_clue_fkey FOREIGN KEY (connects_to_clue) REFERENCES maya_rp.clues(id);


--
-- Name: clues clues_location_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.clues
    ADD CONSTRAINT clues_location_id_fkey FOREIGN KEY (location_id) REFERENCES maya_rp.locations(id);


--
-- Name: clues clues_revealed_by_character_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.clues
    ADD CONSTRAINT clues_revealed_by_character_fkey FOREIGN KEY (revealed_by_character) REFERENCES maya_rp.characters(id);


--
-- Name: clues clues_session_found_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.clues
    ADD CONSTRAINT clues_session_found_fkey FOREIGN KEY (session_found) REFERENCES maya_rp.sessions(id);


--
-- Name: clues clues_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.clues
    ADD CONSTRAINT clues_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: colonies colonies_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.colonies
    ADD CONSTRAINT colonies_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: colonization_projects colonization_projects_planet_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.colonization_projects
    ADD CONSTRAINT colonization_projects_planet_id_fkey FOREIGN KEY (planet_id) REFERENCES maya_rp.planets(id) ON DELETE SET NULL;


--
-- Name: combat_results combat_results_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_results
    ADD CONSTRAINT combat_results_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: combat_results combat_results_tactical_state_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_results
    ADD CONSTRAINT combat_results_tactical_state_id_fkey FOREIGN KEY (tactical_state_id) REFERENCES maya_rp.tactical_states(id);


--
-- Name: combat_rounds combat_rounds_tactical_state_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_rounds
    ADD CONSTRAINT combat_rounds_tactical_state_id_fkey FOREIGN KEY (tactical_state_id) REFERENCES maya_rp.tactical_states(id);


--
-- Name: combat_stats combat_stats_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.combat_stats
    ADD CONSTRAINT combat_stats_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id);


--
-- Name: commodities commodities_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.commodities
    ADD CONSTRAINT commodities_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: complaint_boxes complaint_boxes_planet_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.complaint_boxes
    ADD CONSTRAINT complaint_boxes_planet_id_fkey FOREIGN KEY (planet_id) REFERENCES maya_rp.planets(id);


--
-- Name: complaint_boxes complaint_boxes_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.complaint_boxes
    ADD CONSTRAINT complaint_boxes_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id);


--
-- Name: complaints complaints_box_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.complaints
    ADD CONSTRAINT complaints_box_id_fkey FOREIGN KEY (box_id) REFERENCES maya_rp.complaint_boxes(id);


--
-- Name: consequence_seeds consequence_seeds_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.consequence_seeds
    ADD CONSTRAINT consequence_seeds_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: conversation_log conversation_log_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.conversation_log
    ADD CONSTRAINT conversation_log_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: conversation_log conversation_log_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.conversation_log
    ADD CONSTRAINT conversation_log_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: corporate_assets corporate_assets_corporation_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporate_assets
    ADD CONSTRAINT corporate_assets_corporation_id_fkey FOREIGN KEY (corporation_id) REFERENCES maya_rp.corporations(id) ON DELETE CASCADE;


--
-- Name: corporate_contracts corporate_contracts_corp_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporate_contracts
    ADD CONSTRAINT corporate_contracts_corp_id_fkey FOREIGN KEY (corp_id) REFERENCES maya_rp.corporations(id) ON DELETE CASCADE;


--
-- Name: corporations corporations_ceo_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporations
    ADD CONSTRAINT corporations_ceo_character_id_fkey FOREIGN KEY (ceo_character_id) REFERENCES maya_rp.characters(id);


--
-- Name: corporations corporations_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporations
    ADD CONSTRAINT corporations_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: counter_intel_ops counter_intel_ops_against_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.counter_intel_ops
    ADD CONSTRAINT counter_intel_ops_against_faction_id_fkey FOREIGN KEY (against_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: counter_intel_ops counter_intel_ops_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.counter_intel_ops
    ADD CONSTRAINT counter_intel_ops_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: crew_factions crew_factions_leader_crew_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_factions
    ADD CONSTRAINT crew_factions_leader_crew_id_fkey FOREIGN KEY (leader_crew_id) REFERENCES maya_rp.crew_roster(id);


--
-- Name: crew_factions crew_factions_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_factions
    ADD CONSTRAINT crew_factions_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id);


--
-- Name: crew_roster crew_roster_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_roster
    ADD CONSTRAINT crew_roster_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: crew_roster crew_roster_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crew_roster
    ADD CONSTRAINT crew_roster_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id);


--
-- Name: crisis_events crisis_events_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.crisis_events
    ADD CONSTRAINT crisis_events_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: dark_ops dark_ops_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.dark_ops
    ADD CONSTRAINT dark_ops_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: defense_installations defense_installations_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.defense_installations
    ADD CONSTRAINT defense_installations_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: dig_sites dig_sites_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.dig_sites
    ADD CONSTRAINT dig_sites_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: diplomatic_actions diplomatic_actions_actor_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.diplomatic_actions
    ADD CONSTRAINT diplomatic_actions_actor_faction_id_fkey FOREIGN KEY (actor_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: diplomatic_actions diplomatic_actions_target_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.diplomatic_actions
    ADD CONSTRAINT diplomatic_actions_target_faction_id_fkey FOREIGN KEY (target_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: diplomatic_actions diplomatic_actions_treaty_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.diplomatic_actions
    ADD CONSTRAINT diplomatic_actions_treaty_id_fkey FOREIGN KEY (treaty_id) REFERENCES maya_rp.treaties(id) ON DELETE SET NULL;


--
-- Name: discoveries discoveries_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.discoveries
    ADD CONSTRAINT discoveries_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: duels duels_player_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.duels
    ADD CONSTRAINT duels_player_ship_id_fkey FOREIGN KEY (player_ship_id) REFERENCES maya_rp.ships(id);


--
-- Name: duels duels_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.duels
    ADD CONSTRAINT duels_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: economic_crises economic_crises_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.economic_crises
    ADD CONSTRAINT economic_crises_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: economic_tracker economic_tracker_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.economic_tracker
    ADD CONSTRAINT economic_tracker_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: envoys envoys_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.envoys
    ADD CONSTRAINT envoys_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: envoys envoys_target_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.envoys
    ADD CONSTRAINT envoys_target_faction_id_fkey FOREIGN KEY (target_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: eradication_campaigns eradication_campaigns_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.eradication_campaigns
    ADD CONSTRAINT eradication_campaigns_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: eradication_campaigns eradication_campaigns_target_infestation_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.eradication_campaigns
    ADD CONSTRAINT eradication_campaigns_target_infestation_id_fkey FOREIGN KEY (target_infestation_id) REFERENCES maya_rp.infestation_instances(id) ON DELETE CASCADE;


--
-- Name: escape_countermeasures escape_countermeasures_prisoner_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.escape_countermeasures
    ADD CONSTRAINT escape_countermeasures_prisoner_id_fkey FOREIGN KEY (prisoner_id) REFERENCES maya_rp.prisoners(id);


--
-- Name: escape_countermeasures escape_countermeasures_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.escape_countermeasures
    ADD CONSTRAINT escape_countermeasures_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: espionage_missions espionage_missions_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.espionage_missions
    ADD CONSTRAINT espionage_missions_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id);


--
-- Name: espionage_missions espionage_missions_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.espionage_missions
    ADD CONSTRAINT espionage_missions_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: espionage_operations espionage_operations_spy_network_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.espionage_operations
    ADD CONSTRAINT espionage_operations_spy_network_id_fkey FOREIGN KEY (spy_network_id) REFERENCES maya_rp.spy_networks(id) ON DELETE CASCADE;


--
-- Name: events events_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.events
    ADD CONSTRAINT events_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: faction_ai_state faction_ai_state_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_ai_state
    ADD CONSTRAINT faction_ai_state_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: faction_relations faction_relations_faction_a_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_relations
    ADD CONSTRAINT faction_relations_faction_a_fkey FOREIGN KEY (faction_a) REFERENCES maya_rp.factions(id);


--
-- Name: faction_relations faction_relations_faction_b_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_relations
    ADD CONSTRAINT faction_relations_faction_b_fkey FOREIGN KEY (faction_b) REFERENCES maya_rp.factions(id);


--
-- Name: faction_relations faction_relations_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_relations
    ADD CONSTRAINT faction_relations_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: faction_ships faction_ships_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_ships
    ADD CONSTRAINT faction_ships_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: faction_trade_deals faction_trade_deals_faction_a_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_trade_deals
    ADD CONSTRAINT faction_trade_deals_faction_a_id_fkey FOREIGN KEY (faction_a_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: faction_trade_deals faction_trade_deals_faction_b_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.faction_trade_deals
    ADD CONSTRAINT faction_trade_deals_faction_b_id_fkey FOREIGN KEY (faction_b_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: factions factions_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.factions
    ADD CONSTRAINT factions_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: family_relations family_relations_member_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.family_relations
    ADD CONSTRAINT family_relations_member_id_fkey FOREIGN KEY (member_id) REFERENCES maya_rp.characters(id);


--
-- Name: family_relations family_relations_related_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.family_relations
    ADD CONSTRAINT family_relations_related_id_fkey FOREIGN KEY (related_id) REFERENCES maya_rp.characters(id);


--
-- Name: anti_cloak_grids fk_anti_cloak_grids_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.anti_cloak_grids
    ADD CONSTRAINT fk_anti_cloak_grids_territory FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: artifact_history fk_artifact_history_from; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.artifact_history
    ADD CONSTRAINT fk_artifact_history_from FOREIGN KEY (from_territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: artifact_history fk_artifact_history_to; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.artifact_history
    ADD CONSTRAINT fk_artifact_history_to FOREIGN KEY (to_territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: characters fk_characters_scene_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.characters
    ADD CONSTRAINT fk_characters_scene_territory FOREIGN KEY (scene_territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: corporate_contracts fk_corporate_contracts_target; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.corporate_contracts
    ADD CONSTRAINT fk_corporate_contracts_target FOREIGN KEY (target_territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: defense_installations fk_defense_installations_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.defense_installations
    ADD CONSTRAINT fk_defense_installations_territory FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: governor_applicants fk_governor_applicants_assigned; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.governor_applicants
    ADD CONSTRAINT fk_governor_applicants_assigned FOREIGN KEY (assigned_territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: governor_applicants fk_governor_applicants_home; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.governor_applicants
    ADD CONSTRAINT fk_governor_applicants_home FOREIGN KEY (home_territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: horror_events fk_horror_events_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.horror_events
    ADD CONSTRAINT fk_horror_events_territory FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: incoming_raids fk_incoming_raids_target_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.incoming_raids
    ADD CONSTRAINT fk_incoming_raids_target_territory FOREIGN KEY (target_territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: planets fk_planets_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planets
    ADD CONSTRAINT fk_planets_territory FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: ships fk_ships_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ships
    ADD CONSTRAINT fk_ships_territory FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: sieges fk_sieges_target_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sieges
    ADD CONSTRAINT fk_sieges_target_territory FOREIGN KEY (target_territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: yard_capacity fk_yard_capacity_territory; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.yard_capacity
    ADD CONSTRAINT fk_yard_capacity_territory FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: fleet_members fleet_members_fleet_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleet_members
    ADD CONSTRAINT fleet_members_fleet_id_fkey FOREIGN KEY (fleet_id) REFERENCES maya_rp.fleets(id) ON DELETE CASCADE;


--
-- Name: fleet_members fleet_members_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleet_members
    ADD CONSTRAINT fleet_members_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id) ON DELETE CASCADE;


--
-- Name: fleets fleets_admiral_crew_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleets
    ADD CONSTRAINT fleets_admiral_crew_id_fkey FOREIGN KEY (admiral_crew_id) REFERENCES maya_rp.crew_roster(id);


--
-- Name: fleets fleets_flagship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleets
    ADD CONSTRAINT fleets_flagship_id_fkey FOREIGN KEY (flagship_id) REFERENCES maya_rp.ships(id);


--
-- Name: fleets fleets_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.fleets
    ADD CONSTRAINT fleets_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: global_modifiers global_modifiers_source_research_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.global_modifiers
    ADD CONSTRAINT global_modifiers_source_research_id_fkey FOREIGN KEY (source_research_id) REFERENCES maya_rp.research_projects(id) ON DELETE SET NULL;


--
-- Name: governance_projects governance_projects_decree_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.governance_projects
    ADD CONSTRAINT governance_projects_decree_id_fkey FOREIGN KEY (decree_id) REFERENCES maya_rp.cabinet_decrees(id);


--
-- Name: governance_projects governance_projects_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.governance_projects
    ADD CONSTRAINT governance_projects_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: horror_events horror_events_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.horror_events
    ADD CONSTRAINT horror_events_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: ideology_state ideology_state_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ideology_state
    ADD CONSTRAINT ideology_state_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: image_generations image_generations_prompt_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.image_generations
    ADD CONSTRAINT image_generations_prompt_id_fkey FOREIGN KEY (prompt_id) REFERENCES maya_rp.image_prompts(id);


--
-- Name: image_prompts image_prompts_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.image_prompts
    ADD CONSTRAINT image_prompts_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: incoming_raids incoming_raids_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.incoming_raids
    ADD CONSTRAINT incoming_raids_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: infestation_instances infestation_instances_sector_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_instances
    ADD CONSTRAINT infestation_instances_sector_id_fkey FOREIGN KEY (sector_id) REFERENCES maya_rp.sectors(id) ON DELETE CASCADE;


--
-- Name: infestation_instances infestation_instances_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_instances
    ADD CONSTRAINT infestation_instances_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: infestation_instances infestation_instances_stage_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_instances
    ADD CONSTRAINT infestation_instances_stage_id_fkey FOREIGN KEY (stage_id) REFERENCES maya_rp.infestation_stages(id) ON DELETE CASCADE;


--
-- Name: infestation_instances infestation_instances_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infestation_instances
    ADD CONSTRAINT infestation_instances_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: infrastructure_instances infrastructure_instances_infrastructure_type_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_instances
    ADD CONSTRAINT infrastructure_instances_infrastructure_type_id_fkey FOREIGN KEY (infrastructure_type_id) REFERENCES maya_rp.infrastructure_types(id) ON DELETE CASCADE;


--
-- Name: infrastructure_instances infrastructure_instances_sector_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_instances
    ADD CONSTRAINT infrastructure_instances_sector_id_fkey FOREIGN KEY (sector_id) REFERENCES maya_rp.sectors(id) ON DELETE CASCADE;


--
-- Name: infrastructure_instances infrastructure_instances_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_instances
    ADD CONSTRAINT infrastructure_instances_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: infrastructure_instances infrastructure_instances_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_instances
    ADD CONSTRAINT infrastructure_instances_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: infrastructure_production infrastructure_production_infrastructure_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.infrastructure_production
    ADD CONSTRAINT infrastructure_production_infrastructure_id_fkey FOREIGN KEY (infrastructure_id) REFERENCES maya_rp.infrastructure_instances(id) ON DELETE CASCADE;


--
-- Name: intel_reports intel_reports_recipient_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.intel_reports
    ADD CONSTRAINT intel_reports_recipient_faction_id_fkey FOREIGN KEY (recipient_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: intel_reports intel_reports_source_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.intel_reports
    ADD CONSTRAINT intel_reports_source_faction_id_fkey FOREIGN KEY (source_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: interrogation_log interrogation_log_prisoner_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.interrogation_log
    ADD CONSTRAINT interrogation_log_prisoner_id_fkey FOREIGN KEY (prisoner_id) REFERENCES maya_rp.prisoners(id);


--
-- Name: interrogation_log interrogation_log_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.interrogation_log
    ADD CONSTRAINT interrogation_log_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: interrogation_log interrogation_log_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.interrogation_log
    ADD CONSTRAINT interrogation_log_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id);


--
-- Name: intimacy_events intimacy_events_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.intimacy_events
    ADD CONSTRAINT intimacy_events_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: intimacy_events intimacy_events_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.intimacy_events
    ADD CONSTRAINT intimacy_events_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: investigation_log investigation_log_clue_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.investigation_log
    ADD CONSTRAINT investigation_log_clue_id_fkey FOREIGN KEY (clue_id) REFERENCES maya_rp.clues(id);


--
-- Name: investigation_log investigation_log_investigation_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.investigation_log
    ADD CONSTRAINT investigation_log_investigation_id_fkey FOREIGN KEY (investigation_id) REFERENCES maya_rp.investigations(id);


--
-- Name: investigation_log investigation_log_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.investigation_log
    ADD CONSTRAINT investigation_log_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: investigations investigations_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.investigations
    ADD CONSTRAINT investigations_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: jealousy_states jealousy_states_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.jealousy_states
    ADD CONSTRAINT jealousy_states_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: jealousy_states jealousy_states_rival_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.jealousy_states
    ADD CONSTRAINT jealousy_states_rival_id_fkey FOREIGN KEY (rival_id) REFERENCES maya_rp.characters(id);


--
-- Name: jealousy_states jealousy_states_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.jealousy_states
    ADD CONSTRAINT jealousy_states_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: leader_events leader_events_leader_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.leader_events
    ADD CONSTRAINT leader_events_leader_id_fkey FOREIGN KEY (leader_id) REFERENCES maya_rp.leaders(id) ON DELETE CASCADE;


--
-- Name: leader_events leader_events_new_leader_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.leader_events
    ADD CONSTRAINT leader_events_new_leader_id_fkey FOREIGN KEY (new_leader_id) REFERENCES maya_rp.leaders(id) ON DELETE SET NULL;


--
-- Name: leaders leaders_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.leaders
    ADD CONSTRAINT leaders_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: leaders leaders_heir_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.leaders
    ADD CONSTRAINT leaders_heir_id_fkey FOREIGN KEY (heir_id) REFERENCES maya_rp.leaders(id) ON DELETE SET NULL;


--
-- Name: legendary_artifacts legendary_artifacts_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.legendary_artifacts
    ADD CONSTRAINT legendary_artifacts_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: legio_structure legio_structure_general_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.legio_structure
    ADD CONSTRAINT legio_structure_general_id_fkey FOREIGN KEY (general_id) REFERENCES maya_rp.characters(id);


--
-- Name: locations locations_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.locations
    ADD CONSTRAINT locations_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: material_stockpiles material_stockpiles_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.material_stockpiles
    ADD CONSTRAINT material_stockpiles_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: megastructure_construction megastructure_construction_megastructure_type_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_construction
    ADD CONSTRAINT megastructure_construction_megastructure_type_id_fkey FOREIGN KEY (megastructure_type_id) REFERENCES maya_rp.megastructure_types(id) ON DELETE CASCADE;


--
-- Name: megastructure_construction megastructure_construction_sector_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_construction
    ADD CONSTRAINT megastructure_construction_sector_id_fkey FOREIGN KEY (sector_id) REFERENCES maya_rp.sectors(id) ON DELETE SET NULL;


--
-- Name: megastructure_construction megastructure_construction_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_construction
    ADD CONSTRAINT megastructure_construction_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: megastructure_construction megastructure_construction_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.megastructure_construction
    ADD CONSTRAINT megastructure_construction_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE SET NULL;


--
-- Name: military_expenditure military_expenditure_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.military_expenditure
    ADD CONSTRAINT military_expenditure_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: morale_history morale_history_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.morale_history
    ADD CONSTRAINT morale_history_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: morale_history morale_history_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.morale_history
    ADD CONSTRAINT morale_history_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id);


--
-- Name: morality_log morality_log_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.morality_log
    ADD CONSTRAINT morality_log_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: morality_log morality_log_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.morality_log
    ADD CONSTRAINT morality_log_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: narrative_hooks narrative_hooks_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrative_hooks
    ADD CONSTRAINT narrative_hooks_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: narrative_pacing narrative_pacing_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrative_pacing
    ADD CONSTRAINT narrative_pacing_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: narrative_seeds narrative_seeds_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrative_seeds
    ADD CONSTRAINT narrative_seeds_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: narrator_cost_log narrator_cost_log_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.narrator_cost_log
    ADD CONSTRAINT narrator_cost_log_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: news_articles news_articles_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.news_articles
    ADD CONSTRAINT news_articles_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: npc_internal_state npc_internal_state_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.npc_internal_state
    ADD CONSTRAINT npc_internal_state_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: npc_internal_state npc_internal_state_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.npc_internal_state
    ADD CONSTRAINT npc_internal_state_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: npc_offscreen_interactions npc_offscreen_interactions_character_a_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.npc_offscreen_interactions
    ADD CONSTRAINT npc_offscreen_interactions_character_a_fkey FOREIGN KEY (character_a) REFERENCES maya_rp.characters(id);


--
-- Name: npc_offscreen_interactions npc_offscreen_interactions_character_b_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.npc_offscreen_interactions
    ADD CONSTRAINT npc_offscreen_interactions_character_b_fkey FOREIGN KEY (character_b) REFERENCES maya_rp.characters(id);


--
-- Name: npc_offscreen_interactions npc_offscreen_interactions_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.npc_offscreen_interactions
    ADD CONSTRAINT npc_offscreen_interactions_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: objectives objectives_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.objectives
    ADD CONSTRAINT objectives_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: pirate_activities pirate_activities_trade_route_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_activities
    ADD CONSTRAINT pirate_activities_trade_route_id_fkey FOREIGN KEY (trade_route_id) REFERENCES maya_rp.trade_routes(id);


--
-- Name: pirate_bases pirate_bases_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_bases
    ADD CONSTRAINT pirate_bases_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: pirate_bounties pirate_bounties_claimed_by_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_bounties
    ADD CONSTRAINT pirate_bounties_claimed_by_fkey FOREIGN KEY (claimed_by) REFERENCES maya_rp.factions(id) ON DELETE SET NULL;


--
-- Name: pirate_bounties pirate_bounties_pirate_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_bounties
    ADD CONSTRAINT pirate_bounties_pirate_faction_id_fkey FOREIGN KEY (pirate_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: pirate_extortion pirate_extortion_pirate_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_extortion
    ADD CONSTRAINT pirate_extortion_pirate_faction_id_fkey FOREIGN KEY (pirate_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: pirate_raids pirate_raids_pirate_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pirate_raids
    ADD CONSTRAINT pirate_raids_pirate_faction_id_fkey FOREIGN KEY (pirate_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: planet_features planet_features_planet_type_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_features
    ADD CONSTRAINT planet_features_planet_type_fkey FOREIGN KEY (planet_type) REFERENCES maya_rp.planet_types_catalog(name);


--
-- Name: planet_population planet_population_planet_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_population
    ADD CONSTRAINT planet_population_planet_id_fkey FOREIGN KEY (planet_id) REFERENCES maya_rp.planets(id);


--
-- Name: planet_population planet_population_species_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planet_population
    ADD CONSTRAINT planet_population_species_id_fkey FOREIGN KEY (species_id) REFERENCES maya_rp.species_catalog(id);


--
-- Name: planets planets_planet_type_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planets
    ADD CONSTRAINT planets_planet_type_fkey FOREIGN KEY (planet_type) REFERENCES maya_rp.planet_types_catalog(name);


--
-- Name: planets planets_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.planets
    ADD CONSTRAINT planets_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: player_action_log player_action_log_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_action_log
    ADD CONSTRAINT player_action_log_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: player_context player_context_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_context
    ADD CONSTRAINT player_context_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: player_trades player_trades_commodity_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_trades
    ADD CONSTRAINT player_trades_commodity_id_fkey FOREIGN KEY (commodity_id) REFERENCES maya_rp.commodities(id);


--
-- Name: player_trades player_trades_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.player_trades
    ADD CONSTRAINT player_trades_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: political_factions political_factions_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.political_factions
    ADD CONSTRAINT political_factions_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: political_factions political_factions_leader_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.political_factions
    ADD CONSTRAINT political_factions_leader_id_fkey FOREIGN KEY (leader_id) REFERENCES maya_rp.leaders(id) ON DELETE SET NULL;


--
-- Name: population_sentiment population_sentiment_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.population_sentiment
    ADD CONSTRAINT population_sentiment_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id);


--
-- Name: population_sentiment population_sentiment_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.population_sentiment
    ADD CONSTRAINT population_sentiment_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id);


--
-- Name: port_upgrades port_upgrades_port_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.port_upgrades
    ADD CONSTRAINT port_upgrades_port_id_fkey FOREIGN KEY (port_id) REFERENCES maya_rp.ports(id) ON DELETE CASCADE;


--
-- Name: ports ports_port_type_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ports
    ADD CONSTRAINT ports_port_type_id_fkey FOREIGN KEY (port_type_id) REFERENCES maya_rp.port_types(id) ON DELETE CASCADE;


--
-- Name: ports ports_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ports
    ADD CONSTRAINT ports_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: ports ports_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ports
    ADD CONSTRAINT ports_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: pregnancies pregnancies_mother_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pregnancies
    ADD CONSTRAINT pregnancies_mother_id_fkey FOREIGN KEY (mother_id) REFERENCES maya_rp.characters(id);


--
-- Name: pregnancies pregnancies_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.pregnancies
    ADD CONSTRAINT pregnancies_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: price_history price_history_commodity_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.price_history
    ADD CONSTRAINT price_history_commodity_id_fkey FOREIGN KEY (commodity_id) REFERENCES maya_rp.commodities(id);


--
-- Name: prisoner_intel_pipeline prisoner_intel_pipeline_prisoner_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.prisoner_intel_pipeline
    ADD CONSTRAINT prisoner_intel_pipeline_prisoner_id_fkey FOREIGN KEY (prisoner_id) REFERENCES maya_rp.prisoners(id);


--
-- Name: prisoners prisoners_cell_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.prisoners
    ADD CONSTRAINT prisoners_cell_ship_id_fkey FOREIGN KEY (cell_ship_id) REFERENCES maya_rp.ships(id);


--
-- Name: prisoners prisoners_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.prisoners
    ADD CONSTRAINT prisoners_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: production_consumption_log production_consumption_log_resource_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_consumption_log
    ADD CONSTRAINT production_consumption_log_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES maya_rp.strategic_resources(id);


--
-- Name: production_queue production_queue_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_queue
    ADD CONSTRAINT production_queue_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: production_requirements production_requirements_resource_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.production_requirements
    ADD CONSTRAINT production_requirements_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES maya_rp.strategic_resources(id) ON DELETE CASCADE;


--
-- Name: propaganda_campaigns propaganda_campaigns_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.propaganda_campaigns
    ADD CONSTRAINT propaganda_campaigns_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: public_opinion public_opinion_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.public_opinion
    ADD CONSTRAINT public_opinion_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: quarterly_tasks quarterly_tasks_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.quarterly_tasks
    ADD CONSTRAINT quarterly_tasks_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: quests quests_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.quests
    ADD CONSTRAINT quests_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: raid_log raid_log_raider_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.raid_log
    ADD CONSTRAINT raid_log_raider_faction_id_fkey FOREIGN KEY (raider_faction_id) REFERENCES maya_rp.factions(id);


--
-- Name: raid_log raid_log_supply_line_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.raid_log
    ADD CONSTRAINT raid_log_supply_line_id_fkey FOREIGN KEY (supply_line_id) REFERENCES maya_rp.supply_lines(id);


--
-- Name: raid_log raid_log_target_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.raid_log
    ADD CONSTRAINT raid_log_target_faction_id_fkey FOREIGN KEY (target_faction_id) REFERENCES maya_rp.factions(id);


--
-- Name: reputation_events reputation_events_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.reputation_events
    ADD CONSTRAINT reputation_events_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: research_projects research_projects_prerequisite_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.research_projects
    ADD CONSTRAINT research_projects_prerequisite_id_fkey FOREIGN KEY (prerequisite_id) REFERENCES maya_rp.research_projects(id);


--
-- Name: research_queue research_queue_project_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.research_queue
    ADD CONSTRAINT research_queue_project_id_fkey FOREIGN KEY (project_id) REFERENCES maya_rp.research_projects(id) ON DELETE CASCADE;


--
-- Name: resource_inventory resource_inventory_resource_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.resource_inventory
    ADD CONSTRAINT resource_inventory_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES maya_rp.strategic_resources(id) ON DELETE CASCADE;


--
-- Name: resource_production resource_production_resource_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.resource_production
    ADD CONSTRAINT resource_production_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES maya_rp.strategic_resources(id) ON DELETE SET NULL;


--
-- Name: resources resources_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.resources
    ADD CONSTRAINT resources_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: roll_history roll_history_context_event_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_history
    ADD CONSTRAINT roll_history_context_event_id_fkey FOREIGN KEY (context_event_id) REFERENCES maya_rp.events(id);


--
-- Name: roll_history roll_history_difficulty_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_history
    ADD CONSTRAINT roll_history_difficulty_id_fkey FOREIGN KEY (difficulty_id) REFERENCES maya_rp.difficulty_tiers(id);


--
-- Name: roll_history roll_history_roll_type_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_history
    ADD CONSTRAINT roll_history_roll_type_id_fkey FOREIGN KEY (roll_type_id) REFERENCES maya_rp.roll_types(id);


--
-- Name: roll_history roll_history_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.roll_history
    ADD CONSTRAINT roll_history_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: romance_arcs romance_arcs_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.romance_arcs
    ADD CONSTRAINT romance_arcs_character_id_fkey FOREIGN KEY (character_id) REFERENCES maya_rp.characters(id);


--
-- Name: romance_arcs romance_arcs_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.romance_arcs
    ADD CONSTRAINT romance_arcs_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: savepoints savepoints_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.savepoints
    ADD CONSTRAINT savepoints_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: scene_stack scene_stack_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scene_stack
    ADD CONSTRAINT scene_stack_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: science_missions science_missions_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.science_missions
    ADD CONSTRAINT science_missions_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: science_missions science_missions_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.science_missions
    ADD CONSTRAINT science_missions_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id);


--
-- Name: scientific_theories scientific_theories_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.scientific_theories
    ADD CONSTRAINT scientific_theories_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: score_history score_history_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.score_history
    ADD CONSTRAINT score_history_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: secrets secrets_holder_character_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.secrets
    ADD CONSTRAINT secrets_holder_character_id_fkey FOREIGN KEY (holder_character_id) REFERENCES maya_rp.characters(id);


--
-- Name: secrets secrets_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.secrets
    ADD CONSTRAINT secrets_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: sector_connections sector_connections_from_sector_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_connections
    ADD CONSTRAINT sector_connections_from_sector_id_fkey FOREIGN KEY (from_sector_id) REFERENCES maya_rp.sectors(id);


--
-- Name: sector_connections sector_connections_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_connections
    ADD CONSTRAINT sector_connections_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: sector_connections sector_connections_to_sector_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_connections
    ADD CONSTRAINT sector_connections_to_sector_id_fkey FOREIGN KEY (to_sector_id) REFERENCES maya_rp.sectors(id);


--
-- Name: sector_resources sector_resources_sector_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_resources
    ADD CONSTRAINT sector_resources_sector_id_fkey FOREIGN KEY (sector_id) REFERENCES maya_rp.sectors(id);


--
-- Name: sector_visibility sector_visibility_sector_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_visibility
    ADD CONSTRAINT sector_visibility_sector_id_fkey FOREIGN KEY (sector_id) REFERENCES maya_rp.sectors(id);


--
-- Name: sector_visibility sector_visibility_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sector_visibility
    ADD CONSTRAINT sector_visibility_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: sectors sectors_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sectors
    ADD CONSTRAINT sectors_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: sessions sessions_primary_partner_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sessions
    ADD CONSTRAINT sessions_primary_partner_id_fkey FOREIGN KEY (primary_partner_id) REFERENCES maya_rp.characters(id);


--
-- Name: ship_armaments ship_armaments_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_armaments
    ADD CONSTRAINT ship_armaments_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id) ON DELETE CASCADE;


--
-- Name: ship_armaments ship_armaments_weapon_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_armaments
    ADD CONSTRAINT ship_armaments_weapon_id_fkey FOREIGN KEY (weapon_id) REFERENCES maya_rp.weapons(id);


--
-- Name: ship_modules ship_modules_module_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_modules
    ADD CONSTRAINT ship_modules_module_id_fkey FOREIGN KEY (module_id) REFERENCES maya_rp.modules(id);


--
-- Name: ship_modules ship_modules_ship_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_modules
    ADD CONSTRAINT ship_modules_ship_id_fkey FOREIGN KEY (ship_id) REFERENCES maya_rp.ships(id) ON DELETE CASCADE;


--
-- Name: ship_tech_bonuses ship_tech_bonuses_source_research_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ship_tech_bonuses
    ADD CONSTRAINT ship_tech_bonuses_source_research_id_fkey FOREIGN KEY (source_research_id) REFERENCES maya_rp.research_projects(id) ON DELETE SET NULL;


--
-- Name: ships ships_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ships
    ADD CONSTRAINT ships_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id);


--
-- Name: ships ships_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.ships
    ADD CONSTRAINT ships_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: sieges sieges_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sieges
    ADD CONSTRAINT sieges_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: sieges sieges_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.sieges
    ADD CONSTRAINT sieges_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id);


--
-- Name: slave_births slave_births_parent_slave_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_births
    ADD CONSTRAINT slave_births_parent_slave_id_fkey FOREIGN KEY (parent_slave_id) REFERENCES maya_rp.slaves(id) ON DELETE CASCADE;


--
-- Name: slave_market slave_market_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_market
    ADD CONSTRAINT slave_market_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: slave_revolts slave_revolts_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_revolts
    ADD CONSTRAINT slave_revolts_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: slave_training slave_training_slave_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.slave_training
    ADD CONSTRAINT slave_training_slave_id_fkey FOREIGN KEY (slave_id) REFERENCES maya_rp.slaves(id) ON DELETE CASCADE;


--
-- Name: social_events social_events_diplomatic_action_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.social_events
    ADD CONSTRAINT social_events_diplomatic_action_id_fkey FOREIGN KEY (diplomatic_action_id) REFERENCES maya_rp.diplomatic_actions(id) ON DELETE SET NULL;


--
-- Name: social_events social_events_location_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.social_events
    ADD CONSTRAINT social_events_location_id_fkey FOREIGN KEY (location_id) REFERENCES maya_rp.locations(id);


--
-- Name: social_events social_events_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.social_events
    ADD CONSTRAINT social_events_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: space_lanes space_lanes_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.space_lanes
    ADD CONSTRAINT space_lanes_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: spy_networks spy_networks_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.spy_networks
    ADD CONSTRAINT spy_networks_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: spy_networks spy_networks_target_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.spy_networks
    ADD CONSTRAINT spy_networks_target_faction_id_fkey FOREIGN KEY (target_faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: state state_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.state
    ADD CONSTRAINT state_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: state_snapshots state_snapshots_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.state_snapshots
    ADD CONSTRAINT state_snapshots_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: stealth_units stealth_units_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stealth_units
    ADD CONSTRAINT stealth_units_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: stealth_units stealth_units_unit_type_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stealth_units
    ADD CONSTRAINT stealth_units_unit_type_id_fkey FOREIGN KEY (unit_type_id) REFERENCES maya_rp.stealth_unit_types(id);


--
-- Name: stock_prices stock_prices_resource_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.stock_prices
    ADD CONSTRAINT stock_prices_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES maya_rp.strategic_resources(id) ON DELETE CASCADE;


--
-- Name: story_arcs story_arcs_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_arcs
    ADD CONSTRAINT story_arcs_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: story_checkpoints story_checkpoints_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_checkpoints
    ADD CONSTRAINT story_checkpoints_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: story_log story_log_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.story_log
    ADD CONSTRAINT story_log_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id) ON DELETE CASCADE;


--
-- Name: supply_depots supply_depots_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.supply_depots
    ADD CONSTRAINT supply_depots_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: supply_lines supply_lines_depot_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.supply_lines
    ADD CONSTRAINT supply_lines_depot_id_fkey FOREIGN KEY (depot_id) REFERENCES maya_rp.supply_depots(id);


--
-- Name: tactical_states tactical_states_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tactical_states
    ADD CONSTRAINT tactical_states_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: task_routes task_routes_decree_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.task_routes
    ADD CONSTRAINT task_routes_decree_id_fkey FOREIGN KEY (decree_id) REFERENCES maya_rp.cabinet_decrees(id);


--
-- Name: task_routes task_routes_from_seat_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.task_routes
    ADD CONSTRAINT task_routes_from_seat_fkey FOREIGN KEY (from_seat) REFERENCES maya_rp.cabinet_hierarchy(id);


--
-- Name: task_routes task_routes_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.task_routes
    ADD CONSTRAINT task_routes_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: task_routes task_routes_to_seat_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.task_routes
    ADD CONSTRAINT task_routes_to_seat_fkey FOREIGN KEY (to_seat) REFERENCES maya_rp.cabinet_hierarchy(id);


--
-- Name: tax_history tax_history_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tax_history
    ADD CONSTRAINT tax_history_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: technologies technologies_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.technologies
    ADD CONSTRAINT technologies_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: terraforming_projects terraforming_projects_planet_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.terraforming_projects
    ADD CONSTRAINT terraforming_projects_planet_id_fkey FOREIGN KEY (planet_id) REFERENCES maya_rp.planets(id) ON DELETE SET NULL;


--
-- Name: territory territory_last_battle_session_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory
    ADD CONSTRAINT territory_last_battle_session_fkey FOREIGN KEY (last_battle_session) REFERENCES maya_rp.sessions(id);


--
-- Name: territory territory_location_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory
    ADD CONSTRAINT territory_location_id_fkey FOREIGN KEY (location_id) REFERENCES maya_rp.locations(id);


--
-- Name: territory_modifiers territory_modifiers_source_research_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory_modifiers
    ADD CONSTRAINT territory_modifiers_source_research_id_fkey FOREIGN KEY (source_research_id) REFERENCES maya_rp.research_projects(id) ON DELETE SET NULL;


--
-- Name: territory_modifiers territory_modifiers_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory_modifiers
    ADD CONSTRAINT territory_modifiers_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: territory_resources territory_resources_resource_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory_resources
    ADD CONSTRAINT territory_resources_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES maya_rp.strategic_resources(id) ON DELETE CASCADE;


--
-- Name: territory_resources territory_resources_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory_resources
    ADD CONSTRAINT territory_resources_territory_id_fkey FOREIGN KEY (territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: territory territory_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.territory
    ADD CONSTRAINT territory_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: theme_state theme_state_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.theme_state
    ADD CONSTRAINT theme_state_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: tick_summaries tick_summaries_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.tick_summaries
    ADD CONSTRAINT tick_summaries_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: trade_log trade_log_route_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trade_log
    ADD CONSTRAINT trade_log_route_id_fkey FOREIGN KEY (route_id) REFERENCES maya_rp.trade_routes(id) ON DELETE CASCADE;


--
-- Name: trade_routes trade_routes_destination_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trade_routes
    ADD CONSTRAINT trade_routes_destination_territory_id_fkey FOREIGN KEY (destination_territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: trade_routes trade_routes_origin_territory_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trade_routes
    ADD CONSTRAINT trade_routes_origin_territory_id_fkey FOREIGN KEY (origin_territory_id) REFERENCES maya_rp.territory(id) ON DELETE CASCADE;


--
-- Name: trade_routes trade_routes_resource_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trade_routes
    ADD CONSTRAINT trade_routes_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES maya_rp.strategic_resources(id) ON DELETE CASCADE;


--
-- Name: trait_assignments trait_assignments_trait_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.trait_assignments
    ADD CONSTRAINT trait_assignments_trait_id_fkey FOREIGN KEY (trait_id) REFERENCES maya_rp.trait_catalog(trait_id);


--
-- Name: transport_missions transport_missions_cargo_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.transport_missions
    ADD CONSTRAINT transport_missions_cargo_id_fkey FOREIGN KEY (cargo_id) REFERENCES maya_rp.cargo(id);


--
-- Name: transport_missions transport_missions_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.transport_missions
    ADD CONSTRAINT transport_missions_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: treaties treaties_faction_a_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.treaties
    ADD CONSTRAINT treaties_faction_a_id_fkey FOREIGN KEY (faction_a_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: treaties treaties_faction_b_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.treaties
    ADD CONSTRAINT treaties_faction_b_id_fkey FOREIGN KEY (faction_b_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: victory_tracking victory_tracking_faction_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.victory_tracking
    ADD CONSTRAINT victory_tracking_faction_id_fkey FOREIGN KEY (faction_id) REFERENCES maya_rp.factions(id) ON DELETE CASCADE;


--
-- Name: wars wars_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.wars
    ADD CONSTRAINT wars_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: weapon_upgrades weapon_upgrades_weapon_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapon_upgrades
    ADD CONSTRAINT weapon_upgrades_weapon_id_fkey FOREIGN KEY (weapon_id) REFERENCES maya_rp.weapons(id);


--
-- Name: weapons weapons_kind_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.weapons
    ADD CONSTRAINT weapons_kind_fkey FOREIGN KEY (kind) REFERENCES maya_rp.weapon_kinds(kind);


--
-- Name: world_reactions world_reactions_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.world_reactions
    ADD CONSTRAINT world_reactions_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: wreck_inventory wreck_inventory_session_id_fkey; Type: FK CONSTRAINT; Schema: maya_rp; Owner: -
--

ALTER TABLE ONLY maya_rp.wreck_inventory
    ADD CONSTRAINT wreck_inventory_session_id_fkey FOREIGN KEY (session_id) REFERENCES maya_rp.sessions(id);


--
-- Name: SCHEMA maya_rp; Type: ACL; Schema: -; Owner: -
--

GRANT ALL ON SCHEMA maya_rp TO rp_engine;
GRANT USAGE ON SCHEMA maya_rp TO map_reader;


--
-- Name: TABLE _migrations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp._migrations TO map_reader;


--
-- Name: TABLE academy_campuses; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.academy_campuses TO rp_engine;
GRANT SELECT ON TABLE maya_rp.academy_campuses TO map_reader;


--
-- Name: SEQUENCE academy_campuses_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.academy_campuses_id_seq TO rp_engine;


--
-- Name: TABLE active_disasters; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.active_disasters TO rp_engine;
GRANT SELECT ON TABLE maya_rp.active_disasters TO map_reader;


--
-- Name: SEQUENCE active_disasters_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.active_disasters_id_seq TO rp_engine;


--
-- Name: TABLE active_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.active_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.active_events TO map_reader;


--
-- Name: SEQUENCE active_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.active_events_id_seq TO rp_engine;


--
-- Name: TABLE active_scenes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.active_scenes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.active_scenes TO map_reader;


--
-- Name: SEQUENCE active_scenes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.active_scenes_id_seq TO rp_engine;


--
-- Name: TABLE adjutant_prompts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.adjutant_prompts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.adjutant_prompts TO map_reader;


--
-- Name: SEQUENCE adjutant_prompts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.adjutant_prompts_id_seq TO rp_engine;


--
-- Name: TABLE ai_decision_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ai_decision_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ai_decision_log TO map_reader;


--
-- Name: SEQUENCE ai_decision_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ai_decision_log_id_seq TO rp_engine;


--
-- Name: TABLE ai_decisions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ai_decisions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ai_decisions TO map_reader;


--
-- Name: SEQUENCE ai_decisions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ai_decisions_id_seq TO rp_engine;


--
-- Name: TABLE ai_tactics_history; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ai_tactics_history TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ai_tactics_history TO map_reader;


--
-- Name: SEQUENCE ai_tactics_history_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ai_tactics_history_id_seq TO rp_engine;


--
-- Name: TABLE alchemy_recipes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.alchemy_recipes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.alchemy_recipes TO map_reader;


--
-- Name: SEQUENCE alchemy_recipes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.alchemy_recipes_id_seq TO rp_engine;


--
-- Name: TABLE alert_queue; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.alert_queue TO rp_engine;
GRANT SELECT ON TABLE maya_rp.alert_queue TO map_reader;


--
-- Name: SEQUENCE alert_queue_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.alert_queue_id_seq TO rp_engine;


--
-- Name: TABLE animal_encounters; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.animal_encounters TO rp_engine;
GRANT SELECT ON TABLE maya_rp.animal_encounters TO map_reader;


--
-- Name: SEQUENCE animal_encounters_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.animal_encounters_id_seq TO rp_engine;


--
-- Name: TABLE anomalies_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.anomalies_catalog TO rp_engine;
GRANT SELECT ON TABLE maya_rp.anomalies_catalog TO map_reader;


--
-- Name: SEQUENCE anomalies_catalog_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.anomalies_catalog_id_seq TO rp_engine;


--
-- Name: TABLE anti_cloak_grids; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.anti_cloak_grids TO rp_engine;
GRANT SELECT ON TABLE maya_rp.anti_cloak_grids TO map_reader;


--
-- Name: SEQUENCE anti_cloak_grids_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.anti_cloak_grids_id_seq TO rp_engine;


--
-- Name: TABLE artifact_history; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.artifact_history TO rp_engine;
GRANT SELECT ON TABLE maya_rp.artifact_history TO map_reader;


--
-- Name: SEQUENCE artifact_history_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.artifact_history_id_seq TO rp_engine;


--
-- Name: TABLE artifacts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.artifacts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.artifacts TO map_reader;


--
-- Name: SEQUENCE artifacts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.artifacts_id_seq TO rp_engine;


--
-- Name: TABLE auto_queue; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE maya_rp.auto_queue TO rp_engine;
GRANT SELECT ON TABLE maya_rp.auto_queue TO map_reader;


--
-- Name: SEQUENCE auto_queue_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT,USAGE ON SEQUENCE maya_rp.auto_queue_id_seq TO rp_engine;


--
-- Name: TABLE battle_terrain; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.battle_terrain TO rp_engine;
GRANT SELECT ON TABLE maya_rp.battle_terrain TO map_reader;


--
-- Name: SEQUENCE battle_terrain_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.battle_terrain_id_seq TO rp_engine;


--
-- Name: TABLE bug_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.bug_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.bug_events TO map_reader;


--
-- Name: SEQUENCE bug_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.bug_events_id_seq TO rp_engine;


--
-- Name: TABLE bug_tech_tree; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.bug_tech_tree TO rp_engine;
GRANT SELECT ON TABLE maya_rp.bug_tech_tree TO map_reader;


--
-- Name: SEQUENCE bug_tech_tree_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.bug_tech_tree_id_seq TO rp_engine;


--
-- Name: TABLE bug_war_assets; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.bug_war_assets TO rp_engine;
GRANT SELECT ON TABLE maya_rp.bug_war_assets TO map_reader;


--
-- Name: SEQUENCE bug_war_assets_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.bug_war_assets_id_seq TO rp_engine;


--
-- Name: TABLE build_queue; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.build_queue TO rp_engine;
GRANT SELECT ON TABLE maya_rp.build_queue TO map_reader;


--
-- Name: SEQUENCE build_queue_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.build_queue_id_seq TO rp_engine;


--
-- Name: TABLE build_templates; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.build_templates TO rp_engine;
GRANT SELECT ON TABLE maya_rp.build_templates TO map_reader;


--
-- Name: SEQUENCE build_templates_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.build_templates_id_seq TO rp_engine;


--
-- Name: TABLE cabinet_decrees; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.cabinet_decrees TO rp_engine;
GRANT SELECT ON TABLE maya_rp.cabinet_decrees TO map_reader;


--
-- Name: SEQUENCE cabinet_decrees_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.cabinet_decrees_id_seq TO rp_engine;


--
-- Name: TABLE cabinet_hierarchy; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.cabinet_hierarchy TO rp_engine;
GRANT SELECT ON TABLE maya_rp.cabinet_hierarchy TO map_reader;


--
-- Name: SEQUENCE cabinet_hierarchy_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.cabinet_hierarchy_id_seq TO rp_engine;


--
-- Name: TABLE cabinet_meetings; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.cabinet_meetings TO rp_engine;
GRANT SELECT ON TABLE maya_rp.cabinet_meetings TO map_reader;


--
-- Name: SEQUENCE cabinet_meetings_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.cabinet_meetings_id_seq TO rp_engine;


--
-- Name: TABLE cargo; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.cargo TO rp_engine;
GRANT SELECT ON TABLE maya_rp.cargo TO map_reader;


--
-- Name: SEQUENCE cargo_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.cargo_id_seq TO rp_engine;


--
-- Name: TABLE chapters; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.chapters TO rp_engine;
GRANT SELECT ON TABLE maya_rp.chapters TO map_reader;


--
-- Name: SEQUENCE chapters_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.chapters_id_seq TO rp_engine;


--
-- Name: TABLE character_arcs; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_arcs TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_arcs TO map_reader;


--
-- Name: SEQUENCE character_arcs_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.character_arcs_id_seq TO rp_engine;


--
-- Name: TABLE character_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_events TO map_reader;


--
-- Name: SEQUENCE character_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.character_events_id_seq TO rp_engine;


--
-- Name: TABLE character_injuries; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_injuries TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_injuries TO map_reader;


--
-- Name: SEQUENCE character_injuries_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.character_injuries_id_seq TO rp_engine;


--
-- Name: TABLE character_memories; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_memories TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_memories TO map_reader;


--
-- Name: SEQUENCE character_memories_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.character_memories_id_seq TO rp_engine;


--
-- Name: TABLE character_presence_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_presence_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_presence_log TO map_reader;


--
-- Name: SEQUENCE character_presence_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.character_presence_log_id_seq TO rp_engine;


--
-- Name: TABLE character_quirks; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_quirks TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_quirks TO map_reader;


--
-- Name: SEQUENCE character_quirks_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.character_quirks_id_seq TO rp_engine;


--
-- Name: TABLE character_relationships; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_relationships TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_relationships TO map_reader;


--
-- Name: SEQUENCE character_relationships_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.character_relationships_id_seq TO rp_engine;


--
-- Name: TABLE character_species; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_species TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_species TO map_reader;


--
-- Name: TABLE character_traits; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.character_traits TO rp_engine;
GRANT SELECT ON TABLE maya_rp.character_traits TO map_reader;


--
-- Name: SEQUENCE character_traits_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.character_traits_id_seq TO rp_engine;


--
-- Name: TABLE characters; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.characters TO rp_engine;
GRANT SELECT ON TABLE maya_rp.characters TO map_reader;


--
-- Name: SEQUENCE characters_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.characters_id_seq TO rp_engine;


--
-- Name: TABLE leaders; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.leaders TO rp_engine;
GRANT SELECT ON TABLE maya_rp.leaders TO map_reader;


--
-- Name: TABLE characters_unified; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.characters_unified TO rp_engine;
GRANT SELECT ON TABLE maya_rp.characters_unified TO map_reader;


--
-- Name: TABLE chekhov_elements; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.chekhov_elements TO rp_engine;
GRANT SELECT ON TABLE maya_rp.chekhov_elements TO map_reader;


--
-- Name: SEQUENCE chekhov_elements_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.chekhov_elements_id_seq TO rp_engine;


--
-- Name: TABLE choices; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.choices TO rp_engine;
GRANT SELECT ON TABLE maya_rp.choices TO map_reader;


--
-- Name: SEQUENCE choices_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.choices_id_seq TO rp_engine;


--
-- Name: TABLE clues; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.clues TO rp_engine;
GRANT SELECT ON TABLE maya_rp.clues TO map_reader;


--
-- Name: SEQUENCE clues_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.clues_id_seq TO rp_engine;


--
-- Name: TABLE colonies; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.colonies TO rp_engine;
GRANT SELECT ON TABLE maya_rp.colonies TO map_reader;


--
-- Name: SEQUENCE colonies_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.colonies_id_seq TO rp_engine;


--
-- Name: TABLE colonization_projects; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.colonization_projects TO rp_engine;
GRANT SELECT ON TABLE maya_rp.colonization_projects TO map_reader;


--
-- Name: SEQUENCE colonization_projects_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.colonization_projects_id_seq TO rp_engine;


--
-- Name: TABLE combat_results; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.combat_results TO rp_engine;
GRANT SELECT ON TABLE maya_rp.combat_results TO map_reader;


--
-- Name: SEQUENCE combat_results_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.combat_results_id_seq TO rp_engine;


--
-- Name: TABLE combat_rounds; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.combat_rounds TO rp_engine;
GRANT SELECT ON TABLE maya_rp.combat_rounds TO map_reader;


--
-- Name: SEQUENCE combat_rounds_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.combat_rounds_id_seq TO rp_engine;


--
-- Name: TABLE combat_stats; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.combat_stats TO rp_engine;
GRANT SELECT ON TABLE maya_rp.combat_stats TO map_reader;


--
-- Name: SEQUENCE combat_stats_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.combat_stats_id_seq TO rp_engine;


--
-- Name: TABLE commodities; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.commodities TO rp_engine;
GRANT SELECT ON TABLE maya_rp.commodities TO map_reader;


--
-- Name: SEQUENCE commodities_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.commodities_id_seq TO rp_engine;


--
-- Name: TABLE complaint_boxes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.complaint_boxes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.complaint_boxes TO map_reader;


--
-- Name: SEQUENCE complaint_boxes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.complaint_boxes_id_seq TO rp_engine;


--
-- Name: TABLE complaints; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.complaints TO rp_engine;
GRANT SELECT ON TABLE maya_rp.complaints TO map_reader;


--
-- Name: SEQUENCE complaints_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.complaints_id_seq TO rp_engine;


--
-- Name: TABLE consequence_seeds; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.consequence_seeds TO rp_engine;
GRANT SELECT ON TABLE maya_rp.consequence_seeds TO map_reader;


--
-- Name: SEQUENCE consequence_seeds_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.consequence_seeds_id_seq TO rp_engine;


--
-- Name: TABLE containment_measures; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.containment_measures TO rp_engine;
GRANT SELECT ON TABLE maya_rp.containment_measures TO map_reader;


--
-- Name: SEQUENCE containment_measures_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.containment_measures_id_seq TO rp_engine;


--
-- Name: TABLE conversation_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.conversation_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.conversation_log TO map_reader;


--
-- Name: SEQUENCE conversation_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.conversation_log_id_seq TO rp_engine;


--
-- Name: TABLE corporate_assets; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.corporate_assets TO rp_engine;
GRANT SELECT ON TABLE maya_rp.corporate_assets TO map_reader;


--
-- Name: SEQUENCE corporate_assets_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.corporate_assets_id_seq TO rp_engine;


--
-- Name: TABLE corporate_contracts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE maya_rp.corporate_contracts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.corporate_contracts TO map_reader;


--
-- Name: SEQUENCE corporate_contracts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT,USAGE ON SEQUENCE maya_rp.corporate_contracts_id_seq TO rp_engine;


--
-- Name: TABLE corporations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.corporations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.corporations TO map_reader;


--
-- Name: SEQUENCE corporations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.corporations_id_seq TO rp_engine;


--
-- Name: TABLE counter_intel_ops; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.counter_intel_ops TO rp_engine;
GRANT SELECT ON TABLE maya_rp.counter_intel_ops TO map_reader;


--
-- Name: SEQUENCE counter_intel_ops_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.counter_intel_ops_id_seq TO rp_engine;


--
-- Name: TABLE crew_allocation_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.crew_allocation_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.crew_allocation_log TO map_reader;


--
-- Name: SEQUENCE crew_allocation_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.crew_allocation_log_id_seq TO rp_engine;


--
-- Name: TABLE crew_consumption_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.crew_consumption_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.crew_consumption_log TO map_reader;


--
-- Name: SEQUENCE crew_consumption_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.crew_consumption_log_id_seq TO rp_engine;


--
-- Name: TABLE crew_factions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.crew_factions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.crew_factions TO map_reader;


--
-- Name: SEQUENCE crew_factions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.crew_factions_id_seq TO rp_engine;


--
-- Name: TABLE crew_production_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.crew_production_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.crew_production_log TO map_reader;


--
-- Name: SEQUENCE crew_production_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.crew_production_log_id_seq TO rp_engine;


--
-- Name: TABLE crew_roster; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.crew_roster TO rp_engine;
GRANT SELECT ON TABLE maya_rp.crew_roster TO map_reader;


--
-- Name: SEQUENCE crew_roster_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.crew_roster_id_seq TO rp_engine;


--
-- Name: TABLE crew_skills; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.crew_skills TO rp_engine;
GRANT SELECT ON TABLE maya_rp.crew_skills TO map_reader;


--
-- Name: SEQUENCE crew_skills_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.crew_skills_id_seq TO rp_engine;


--
-- Name: TABLE crew_xp_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.crew_xp_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.crew_xp_log TO map_reader;


--
-- Name: SEQUENCE crew_xp_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.crew_xp_log_id_seq TO rp_engine;


--
-- Name: TABLE crisis_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.crisis_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.crisis_events TO map_reader;


--
-- Name: SEQUENCE crisis_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.crisis_events_id_seq TO rp_engine;


--
-- Name: TABLE damage_resistances; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.damage_resistances TO rp_engine;
GRANT SELECT ON TABLE maya_rp.damage_resistances TO map_reader;


--
-- Name: SEQUENCE damage_resistances_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.damage_resistances_id_seq TO rp_engine;


--
-- Name: TABLE dark_ops; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.dark_ops TO rp_engine;
GRANT SELECT ON TABLE maya_rp.dark_ops TO map_reader;


--
-- Name: SEQUENCE dark_ops_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.dark_ops_id_seq TO rp_engine;


--
-- Name: TABLE defense_installations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.defense_installations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.defense_installations TO map_reader;


--
-- Name: SEQUENCE defense_installations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.defense_installations_id_seq TO rp_engine;


--
-- Name: TABLE difficulty_tiers; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.difficulty_tiers TO rp_engine;
GRANT SELECT ON TABLE maya_rp.difficulty_tiers TO map_reader;


--
-- Name: SEQUENCE difficulty_tiers_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.difficulty_tiers_id_seq TO rp_engine;


--
-- Name: TABLE dig_sites; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.dig_sites TO rp_engine;
GRANT SELECT ON TABLE maya_rp.dig_sites TO map_reader;


--
-- Name: SEQUENCE dig_sites_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.dig_sites_id_seq TO rp_engine;


--
-- Name: TABLE diplomatic_actions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.diplomatic_actions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.diplomatic_actions TO map_reader;


--
-- Name: SEQUENCE diplomatic_actions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.diplomatic_actions_id_seq TO rp_engine;


--
-- Name: TABLE factions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.factions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.factions TO map_reader;


--
-- Name: TABLE treaties; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.treaties TO rp_engine;
GRANT SELECT ON TABLE maya_rp.treaties TO map_reader;


--
-- Name: TABLE diplomatic_overview; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.diplomatic_overview TO rp_engine;
GRANT SELECT ON TABLE maya_rp.diplomatic_overview TO map_reader;


--
-- Name: TABLE disaster_templates; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.disaster_templates TO rp_engine;
GRANT SELECT ON TABLE maya_rp.disaster_templates TO map_reader;


--
-- Name: SEQUENCE disaster_templates_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.disaster_templates_id_seq TO rp_engine;


--
-- Name: TABLE discoveries; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.discoveries TO rp_engine;
GRANT SELECT ON TABLE maya_rp.discoveries TO map_reader;


--
-- Name: SEQUENCE discoveries_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.discoveries_id_seq TO rp_engine;


--
-- Name: TABLE duels; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.duels TO rp_engine;
GRANT SELECT ON TABLE maya_rp.duels TO map_reader;


--
-- Name: SEQUENCE duels_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.duels_id_seq TO rp_engine;


--
-- Name: TABLE economic_crises; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.economic_crises TO rp_engine;
GRANT SELECT ON TABLE maya_rp.economic_crises TO map_reader;


--
-- Name: SEQUENCE economic_crises_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.economic_crises_id_seq TO rp_engine;


--
-- Name: TABLE territory; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.territory TO rp_engine;
GRANT SELECT ON TABLE maya_rp.territory TO map_reader;


--
-- Name: TABLE economic_dashboard; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.economic_dashboard TO rp_engine;
GRANT SELECT ON TABLE maya_rp.economic_dashboard TO map_reader;


--
-- Name: TABLE economic_overview; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.economic_overview TO rp_engine;
GRANT SELECT ON TABLE maya_rp.economic_overview TO map_reader;


--
-- Name: TABLE economic_tracker; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.economic_tracker TO rp_engine;
GRANT SELECT ON TABLE maya_rp.economic_tracker TO map_reader;


--
-- Name: SEQUENCE economic_tracker_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.economic_tracker_id_seq TO rp_engine;


--
-- Name: TABLE enrolled_crew; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.enrolled_crew TO rp_engine;
GRANT SELECT ON TABLE maya_rp.enrolled_crew TO map_reader;


--
-- Name: SEQUENCE enrolled_crew_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.enrolled_crew_id_seq TO rp_engine;


--
-- Name: TABLE envoys; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.envoys TO rp_engine;
GRANT SELECT ON TABLE maya_rp.envoys TO map_reader;


--
-- Name: SEQUENCE envoys_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.envoys_id_seq TO rp_engine;


--
-- Name: TABLE eradication_campaigns; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.eradication_campaigns TO rp_engine;
GRANT SELECT ON TABLE maya_rp.eradication_campaigns TO map_reader;


--
-- Name: SEQUENCE eradication_campaigns_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.eradication_campaigns_id_seq TO rp_engine;


--
-- Name: TABLE escape_countermeasures; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.escape_countermeasures TO rp_engine;
GRANT SELECT ON TABLE maya_rp.escape_countermeasures TO map_reader;


--
-- Name: SEQUENCE escape_countermeasures_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.escape_countermeasures_id_seq TO rp_engine;


--
-- Name: TABLE espionage_missions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.espionage_missions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.espionage_missions TO map_reader;


--
-- Name: SEQUENCE espionage_missions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.espionage_missions_id_seq TO rp_engine;


--
-- Name: TABLE espionage_operations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.espionage_operations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.espionage_operations TO map_reader;


--
-- Name: SEQUENCE espionage_operations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.espionage_operations_id_seq TO rp_engine;


--
-- Name: TABLE event_templates; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.event_templates TO rp_engine;
GRANT SELECT ON TABLE maya_rp.event_templates TO map_reader;


--
-- Name: SEQUENCE event_templates_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.event_templates_id_seq TO rp_engine;


--
-- Name: TABLE events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.events TO map_reader;


--
-- Name: SEQUENCE events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.events_id_seq TO rp_engine;


--
-- Name: TABLE faction_ai_state; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.faction_ai_state TO rp_engine;
GRANT SELECT ON TABLE maya_rp.faction_ai_state TO map_reader;


--
-- Name: SEQUENCE faction_ai_state_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.faction_ai_state_id_seq TO rp_engine;


--
-- Name: TABLE faction_policies; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.faction_policies TO rp_engine;
GRANT SELECT ON TABLE maya_rp.faction_policies TO map_reader;


--
-- Name: SEQUENCE faction_policies_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.faction_policies_id_seq TO rp_engine;


--
-- Name: TABLE faction_relations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.faction_relations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.faction_relations TO map_reader;


--
-- Name: SEQUENCE faction_relations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.faction_relations_id_seq TO rp_engine;


--
-- Name: TABLE faction_ships; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.faction_ships TO rp_engine;
GRANT SELECT ON TABLE maya_rp.faction_ships TO map_reader;


--
-- Name: SEQUENCE faction_ships_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.faction_ships_id_seq TO rp_engine;


--
-- Name: TABLE faction_slave_policy; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.faction_slave_policy TO rp_engine;
GRANT SELECT ON TABLE maya_rp.faction_slave_policy TO map_reader;


--
-- Name: SEQUENCE faction_slave_policy_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.faction_slave_policy_id_seq TO rp_engine;


--
-- Name: TABLE faction_species_rights; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.faction_species_rights TO rp_engine;
GRANT SELECT ON TABLE maya_rp.faction_species_rights TO map_reader;


--
-- Name: SEQUENCE faction_species_rights_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.faction_species_rights_id_seq TO rp_engine;


--
-- Name: TABLE faction_trade_deals; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.faction_trade_deals TO rp_engine;
GRANT SELECT ON TABLE maya_rp.faction_trade_deals TO map_reader;


--
-- Name: SEQUENCE faction_trade_deals_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.faction_trade_deals_id_seq TO rp_engine;


--
-- Name: SEQUENCE factions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.factions_id_seq TO rp_engine;


--
-- Name: TABLE family_relations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.family_relations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.family_relations TO map_reader;


--
-- Name: SEQUENCE family_relations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.family_relations_id_seq TO rp_engine;


--
-- Name: TABLE fleet_formations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.fleet_formations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.fleet_formations TO map_reader;


--
-- Name: SEQUENCE fleet_formations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.fleet_formations_id_seq TO rp_engine;


--
-- Name: TABLE fleet_members; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.fleet_members TO rp_engine;
GRANT SELECT ON TABLE maya_rp.fleet_members TO map_reader;


--
-- Name: SEQUENCE fleet_members_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.fleet_members_id_seq TO rp_engine;


--
-- Name: TABLE fleets; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.fleets TO rp_engine;
GRANT SELECT ON TABLE maya_rp.fleets TO map_reader;


--
-- Name: SEQUENCE fleets_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.fleets_id_seq TO rp_engine;


--
-- Name: TABLE global_modifiers; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.global_modifiers TO rp_engine;
GRANT SELECT ON TABLE maya_rp.global_modifiers TO map_reader;


--
-- Name: SEQUENCE global_modifiers_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.global_modifiers_id_seq TO rp_engine;


--
-- Name: TABLE global_settings; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.global_settings TO rp_engine;
GRANT SELECT ON TABLE maya_rp.global_settings TO map_reader;


--
-- Name: TABLE governance_projects; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.governance_projects TO rp_engine;
GRANT SELECT ON TABLE maya_rp.governance_projects TO map_reader;


--
-- Name: SEQUENCE governance_projects_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.governance_projects_id_seq TO rp_engine;


--
-- Name: TABLE governor_applicants; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.governor_applicants TO map_reader;


--
-- Name: TABLE grand_plan; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.grand_plan TO rp_engine;
GRANT SELECT ON TABLE maya_rp.grand_plan TO map_reader;


--
-- Name: SEQUENCE grand_plan_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.grand_plan_id_seq TO rp_engine;


--
-- Name: TABLE guardrail_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.guardrail_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.guardrail_log TO map_reader;


--
-- Name: SEQUENCE guardrail_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.guardrail_log_id_seq TO rp_engine;


--
-- Name: TABLE horror_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.horror_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.horror_events TO map_reader;


--
-- Name: SEQUENCE horror_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.horror_events_id_seq TO rp_engine;


--
-- Name: TABLE ideology_state; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ideology_state TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ideology_state TO map_reader;


--
-- Name: TABLE image_generations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.image_generations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.image_generations TO map_reader;


--
-- Name: SEQUENCE image_generations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.image_generations_id_seq TO rp_engine;


--
-- Name: TABLE image_prompts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.image_prompts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.image_prompts TO map_reader;


--
-- Name: SEQUENCE image_prompts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.image_prompts_id_seq TO rp_engine;


--
-- Name: TABLE incoming_raids; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.incoming_raids TO rp_engine;
GRANT SELECT ON TABLE maya_rp.incoming_raids TO map_reader;


--
-- Name: SEQUENCE incoming_raids_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.incoming_raids_id_seq TO rp_engine;


--
-- Name: TABLE infestation_instances; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.infestation_instances TO rp_engine;
GRANT SELECT ON TABLE maya_rp.infestation_instances TO map_reader;


--
-- Name: SEQUENCE infestation_instances_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.infestation_instances_id_seq TO rp_engine;


--
-- Name: TABLE infestation_stages; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.infestation_stages TO rp_engine;
GRANT SELECT ON TABLE maya_rp.infestation_stages TO map_reader;


--
-- Name: SEQUENCE infestation_stages_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.infestation_stages_id_seq TO rp_engine;


--
-- Name: TABLE sectors; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.sectors TO rp_engine;
GRANT SELECT ON TABLE maya_rp.sectors TO map_reader;


--
-- Name: TABLE infestation_threats; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.infestation_threats TO rp_engine;
GRANT SELECT ON TABLE maya_rp.infestation_threats TO map_reader;


--
-- Name: TABLE infrastructure_instances; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.infrastructure_instances TO rp_engine;
GRANT SELECT ON TABLE maya_rp.infrastructure_instances TO map_reader;


--
-- Name: SEQUENCE infrastructure_instances_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.infrastructure_instances_id_seq TO rp_engine;


--
-- Name: TABLE infrastructure_types; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.infrastructure_types TO rp_engine;
GRANT SELECT ON TABLE maya_rp.infrastructure_types TO map_reader;


--
-- Name: TABLE infrastructure_overview; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.infrastructure_overview TO rp_engine;
GRANT SELECT ON TABLE maya_rp.infrastructure_overview TO map_reader;


--
-- Name: TABLE infrastructure_production; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.infrastructure_production TO rp_engine;
GRANT SELECT ON TABLE maya_rp.infrastructure_production TO map_reader;


--
-- Name: SEQUENCE infrastructure_production_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.infrastructure_production_id_seq TO rp_engine;


--
-- Name: SEQUENCE infrastructure_types_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.infrastructure_types_id_seq TO rp_engine;


--
-- Name: TABLE intel_reports; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.intel_reports TO rp_engine;
GRANT SELECT ON TABLE maya_rp.intel_reports TO map_reader;


--
-- Name: SEQUENCE intel_reports_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.intel_reports_id_seq TO rp_engine;


--
-- Name: TABLE interrogation_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.interrogation_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.interrogation_log TO map_reader;


--
-- Name: SEQUENCE interrogation_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.interrogation_log_id_seq TO rp_engine;


--
-- Name: TABLE intimacy_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.intimacy_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.intimacy_events TO map_reader;


--
-- Name: SEQUENCE intimacy_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.intimacy_events_id_seq TO rp_engine;


--
-- Name: TABLE investigation_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.investigation_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.investigation_log TO map_reader;


--
-- Name: SEQUENCE investigation_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.investigation_log_id_seq TO rp_engine;


--
-- Name: TABLE investigations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.investigations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.investigations TO map_reader;


--
-- Name: SEQUENCE investigations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.investigations_id_seq TO rp_engine;


--
-- Name: TABLE jealousy_states; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.jealousy_states TO rp_engine;
GRANT SELECT ON TABLE maya_rp.jealousy_states TO map_reader;


--
-- Name: SEQUENCE jealousy_states_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.jealousy_states_id_seq TO rp_engine;


--
-- Name: TABLE leader_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.leader_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.leader_events TO map_reader;


--
-- Name: SEQUENCE leader_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.leader_events_id_seq TO rp_engine;


--
-- Name: SEQUENCE leaders_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.leaders_id_seq TO rp_engine;


--
-- Name: TABLE legendary_artifacts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.legendary_artifacts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.legendary_artifacts TO map_reader;


--
-- Name: SEQUENCE legendary_artifacts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.legendary_artifacts_id_seq TO rp_engine;


--
-- Name: TABLE legio_structure; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.legio_structure TO rp_engine;
GRANT SELECT ON TABLE maya_rp.legio_structure TO map_reader;


--
-- Name: SEQUENCE legio_structure_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.legio_structure_id_seq TO rp_engine;


--
-- Name: TABLE legion_snapshot; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.legion_snapshot TO map_reader;


--
-- Name: TABLE location_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.location_catalog TO rp_engine;
GRANT SELECT ON TABLE maya_rp.location_catalog TO map_reader;


--
-- Name: TABLE locations; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.locations TO rp_engine;
GRANT SELECT ON TABLE maya_rp.locations TO map_reader;


--
-- Name: SEQUENCE locations_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.locations_id_seq TO rp_engine;


--
-- Name: TABLE material_stockpiles; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.material_stockpiles TO rp_engine;
GRANT SELECT ON TABLE maya_rp.material_stockpiles TO map_reader;


--
-- Name: SEQUENCE material_stockpiles_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.material_stockpiles_id_seq TO rp_engine;


--
-- Name: TABLE materials; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.materials TO rp_engine;
GRANT SELECT ON TABLE maya_rp.materials TO map_reader;


--
-- Name: SEQUENCE materials_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.materials_id_seq TO rp_engine;


--
-- Name: TABLE megastructure_construction; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.megastructure_construction TO rp_engine;
GRANT SELECT ON TABLE maya_rp.megastructure_construction TO map_reader;


--
-- Name: SEQUENCE megastructure_construction_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.megastructure_construction_id_seq TO rp_engine;


--
-- Name: TABLE megastructure_types; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.megastructure_types TO rp_engine;
GRANT SELECT ON TABLE maya_rp.megastructure_types TO map_reader;


--
-- Name: TABLE megastructure_status; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.megastructure_status TO rp_engine;
GRANT SELECT ON TABLE maya_rp.megastructure_status TO map_reader;


--
-- Name: SEQUENCE megastructure_types_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.megastructure_types_id_seq TO rp_engine;


--
-- Name: TABLE migration_hashes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.migration_hashes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.migration_hashes TO map_reader;


--
-- Name: TABLE migration_versions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.migration_versions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.migration_versions TO map_reader;


--
-- Name: SEQUENCE migration_versions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.migration_versions_id_seq TO rp_engine;


--
-- Name: TABLE military_expenditure; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.military_expenditure TO rp_engine;
GRANT SELECT ON TABLE maya_rp.military_expenditure TO map_reader;


--
-- Name: SEQUENCE military_expenditure_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.military_expenditure_id_seq TO rp_engine;


--
-- Name: TABLE modules; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.modules TO rp_engine;
GRANT SELECT ON TABLE maya_rp.modules TO map_reader;


--
-- Name: SEQUENCE modules_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.modules_id_seq TO rp_engine;


--
-- Name: TABLE morale_history; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.morale_history TO rp_engine;
GRANT SELECT ON TABLE maya_rp.morale_history TO map_reader;


--
-- Name: SEQUENCE morale_history_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.morale_history_id_seq TO rp_engine;


--
-- Name: TABLE morality_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.morality_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.morality_log TO map_reader;


--
-- Name: SEQUENCE morality_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.morality_log_id_seq TO rp_engine;


--
-- Name: TABLE mystery_templates; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.mystery_templates TO rp_engine;
GRANT SELECT ON TABLE maya_rp.mystery_templates TO map_reader;


--
-- Name: SEQUENCE mystery_templates_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.mystery_templates_id_seq TO rp_engine;


--
-- Name: TABLE narrative_hooks; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.narrative_hooks TO rp_engine;
GRANT SELECT ON TABLE maya_rp.narrative_hooks TO map_reader;


--
-- Name: SEQUENCE narrative_hooks_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.narrative_hooks_id_seq TO rp_engine;


--
-- Name: TABLE narrative_pacing; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.narrative_pacing TO rp_engine;
GRANT SELECT ON TABLE maya_rp.narrative_pacing TO map_reader;


--
-- Name: TABLE narrative_seeds; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.narrative_seeds TO rp_engine;
GRANT SELECT ON TABLE maya_rp.narrative_seeds TO map_reader;


--
-- Name: SEQUENCE narrative_seeds_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.narrative_seeds_id_seq TO rp_engine;


--
-- Name: TABLE narrator_cost_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.narrator_cost_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.narrator_cost_log TO map_reader;


--
-- Name: SEQUENCE narrator_cost_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.narrator_cost_log_id_seq TO rp_engine;


--
-- Name: TABLE news_articles; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.news_articles TO rp_engine;
GRANT SELECT ON TABLE maya_rp.news_articles TO map_reader;


--
-- Name: SEQUENCE news_articles_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.news_articles_id_seq TO rp_engine;


--
-- Name: TABLE npc_internal_state; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.npc_internal_state TO rp_engine;
GRANT SELECT ON TABLE maya_rp.npc_internal_state TO map_reader;


--
-- Name: TABLE npc_offscreen_interactions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.npc_offscreen_interactions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.npc_offscreen_interactions TO map_reader;


--
-- Name: SEQUENCE npc_offscreen_interactions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.npc_offscreen_interactions_id_seq TO rp_engine;


--
-- Name: TABLE objectives; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.objectives TO rp_engine;
GRANT SELECT ON TABLE maya_rp.objectives TO map_reader;


--
-- Name: SEQUENCE objectives_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.objectives_id_seq TO rp_engine;


--
-- Name: TABLE pirate_activities; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_activities TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_activities TO map_reader;


--
-- Name: SEQUENCE pirate_activities_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_activities_id_seq TO rp_engine;


--
-- Name: TABLE pirate_alerts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_alerts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_alerts TO map_reader;


--
-- Name: SEQUENCE pirate_alerts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_alerts_id_seq TO rp_engine;


--
-- Name: TABLE pirate_artifacts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_artifacts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_artifacts TO map_reader;


--
-- Name: SEQUENCE pirate_artifacts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_artifacts_id_seq TO rp_engine;


--
-- Name: TABLE pirate_bases; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_bases TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_bases TO map_reader;


--
-- Name: SEQUENCE pirate_bases_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_bases_id_seq TO rp_engine;


--
-- Name: TABLE pirate_bounties; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_bounties TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_bounties TO map_reader;


--
-- Name: SEQUENCE pirate_bounties_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_bounties_id_seq TO rp_engine;


--
-- Name: TABLE pirate_extortion; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_extortion TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_extortion TO map_reader;


--
-- Name: SEQUENCE pirate_extortion_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_extortion_id_seq TO rp_engine;


--
-- Name: TABLE pirate_fleet_templates; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_fleet_templates TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_fleet_templates TO map_reader;


--
-- Name: SEQUENCE pirate_fleet_templates_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_fleet_templates_id_seq TO rp_engine;


--
-- Name: TABLE pirate_loot_tables; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_loot_tables TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_loot_tables TO map_reader;


--
-- Name: SEQUENCE pirate_loot_tables_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_loot_tables_id_seq TO rp_engine;


--
-- Name: TABLE pirate_raids; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_raids TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_raids TO map_reader;


--
-- Name: SEQUENCE pirate_raids_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_raids_id_seq TO rp_engine;


--
-- Name: TABLE pirate_salvage_templates; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_salvage_templates TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_salvage_templates TO map_reader;


--
-- Name: SEQUENCE pirate_salvage_templates_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_salvage_templates_id_seq TO rp_engine;


--
-- Name: TABLE pirate_ship_classes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_ship_classes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_ship_classes TO map_reader;


--
-- Name: SEQUENCE pirate_ship_classes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_ship_classes_id_seq TO rp_engine;


--
-- Name: TABLE pirate_zones; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.pirate_zones TO rp_engine;
GRANT SELECT ON TABLE maya_rp.pirate_zones TO map_reader;


--
-- Name: SEQUENCE pirate_zones_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.pirate_zones_id_seq TO rp_engine;


--
-- Name: TABLE planet_features; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.planet_features TO rp_engine;
GRANT SELECT ON TABLE maya_rp.planet_features TO map_reader;


--
-- Name: SEQUENCE planet_features_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.planet_features_id_seq TO rp_engine;


--
-- Name: TABLE planet_population; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.planet_population TO rp_engine;
GRANT SELECT ON TABLE maya_rp.planet_population TO map_reader;


--
-- Name: SEQUENCE planet_population_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.planet_population_id_seq TO rp_engine;


--
-- Name: TABLE planet_types_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.planet_types_catalog TO rp_engine;
GRANT SELECT ON TABLE maya_rp.planet_types_catalog TO map_reader;


--
-- Name: TABLE planets; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.planets TO rp_engine;
GRANT SELECT ON TABLE maya_rp.planets TO map_reader;


--
-- Name: SEQUENCE planets_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.planets_id_seq TO rp_engine;


--
-- Name: TABLE player_action_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.player_action_catalog TO map_reader;


--
-- Name: TABLE player_action_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.player_action_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.player_action_log TO map_reader;


--
-- Name: SEQUENCE player_action_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.player_action_log_id_seq TO rp_engine;


--
-- Name: TABLE player_context; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.player_context TO rp_engine;
GRANT SELECT ON TABLE maya_rp.player_context TO map_reader;


--
-- Name: TABLE player_trades; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.player_trades TO rp_engine;
GRANT SELECT ON TABLE maya_rp.player_trades TO map_reader;


--
-- Name: SEQUENCE player_trades_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.player_trades_id_seq TO rp_engine;


--
-- Name: TABLE policy_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.policy_catalog TO rp_engine;
GRANT SELECT ON TABLE maya_rp.policy_catalog TO map_reader;


--
-- Name: SEQUENCE policy_catalog_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.policy_catalog_id_seq TO rp_engine;


--
-- Name: TABLE policy_registry; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.policy_registry TO map_reader;


--
-- Name: TABLE political_factions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.political_factions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.political_factions TO map_reader;


--
-- Name: SEQUENCE political_factions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.political_factions_id_seq TO rp_engine;


--
-- Name: TABLE population_sentiment; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.population_sentiment TO map_reader;


--
-- Name: TABLE port_types; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.port_types TO rp_engine;
GRANT SELECT ON TABLE maya_rp.port_types TO map_reader;


--
-- Name: TABLE ports; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ports TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ports TO map_reader;


--
-- Name: TABLE port_overview; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.port_overview TO rp_engine;
GRANT SELECT ON TABLE maya_rp.port_overview TO map_reader;


--
-- Name: SEQUENCE port_types_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.port_types_id_seq TO rp_engine;


--
-- Name: TABLE port_upgrades; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.port_upgrades TO rp_engine;
GRANT SELECT ON TABLE maya_rp.port_upgrades TO map_reader;


--
-- Name: SEQUENCE port_upgrades_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.port_upgrades_id_seq TO rp_engine;


--
-- Name: SEQUENCE ports_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ports_id_seq TO rp_engine;


--
-- Name: TABLE pregnancies; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.pregnancies TO map_reader;


--
-- Name: TABLE price_history; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.price_history TO rp_engine;
GRANT SELECT ON TABLE maya_rp.price_history TO map_reader;


--
-- Name: SEQUENCE price_history_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.price_history_id_seq TO rp_engine;


--
-- Name: TABLE prisoner_intel_pipeline; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.prisoner_intel_pipeline TO rp_engine;
GRANT SELECT ON TABLE maya_rp.prisoner_intel_pipeline TO map_reader;


--
-- Name: SEQUENCE prisoner_intel_pipeline_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.prisoner_intel_pipeline_id_seq TO rp_engine;


--
-- Name: TABLE prisoners; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.prisoners TO rp_engine;
GRANT SELECT ON TABLE maya_rp.prisoners TO map_reader;


--
-- Name: SEQUENCE prisoners_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.prisoners_id_seq TO rp_engine;


--
-- Name: TABLE production_consumption_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.production_consumption_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.production_consumption_log TO map_reader;


--
-- Name: SEQUENCE production_consumption_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.production_consumption_log_id_seq TO rp_engine;


--
-- Name: TABLE production_lines; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.production_lines TO rp_engine;
GRANT SELECT ON TABLE maya_rp.production_lines TO map_reader;


--
-- Name: SEQUENCE production_lines_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.production_lines_id_seq TO rp_engine;


--
-- Name: TABLE production_queue; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.production_queue TO rp_engine;
GRANT SELECT ON TABLE maya_rp.production_queue TO map_reader;


--
-- Name: SEQUENCE production_queue_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.production_queue_id_seq TO rp_engine;


--
-- Name: TABLE production_requirements; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.production_requirements TO rp_engine;
GRANT SELECT ON TABLE maya_rp.production_requirements TO map_reader;


--
-- Name: SEQUENCE production_requirements_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.production_requirements_id_seq TO rp_engine;


--
-- Name: TABLE propaganda_campaigns; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.propaganda_campaigns TO rp_engine;
GRANT SELECT ON TABLE maya_rp.propaganda_campaigns TO map_reader;


--
-- Name: SEQUENCE propaganda_campaigns_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.propaganda_campaigns_id_seq TO rp_engine;


--
-- Name: TABLE public_opinion; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.public_opinion TO rp_engine;
GRANT SELECT ON TABLE maya_rp.public_opinion TO map_reader;


--
-- Name: SEQUENCE public_opinion_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.public_opinion_id_seq TO rp_engine;


--
-- Name: TABLE quarterly_tasks; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.quarterly_tasks TO rp_engine;
GRANT SELECT ON TABLE maya_rp.quarterly_tasks TO map_reader;


--
-- Name: SEQUENCE quarterly_tasks_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.quarterly_tasks_id_seq TO rp_engine;


--
-- Name: TABLE quests; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.quests TO rp_engine;
GRANT SELECT ON TABLE maya_rp.quests TO map_reader;


--
-- Name: SEQUENCE quests_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.quests_id_seq TO rp_engine;


--
-- Name: TABLE raid_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.raid_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.raid_log TO map_reader;


--
-- Name: SEQUENCE raid_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.raid_log_id_seq TO rp_engine;


--
-- Name: TABLE recipes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.recipes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.recipes TO map_reader;


--
-- Name: SEQUENCE recipes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.recipes_id_seq TO rp_engine;


--
-- Name: TABLE refill_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.refill_log TO map_reader;


--
-- Name: TABLE reputation_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.reputation_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.reputation_events TO map_reader;


--
-- Name: SEQUENCE reputation_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.reputation_events_id_seq TO rp_engine;


--
-- Name: TABLE research_labs; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.research_labs TO rp_engine;
GRANT SELECT ON TABLE maya_rp.research_labs TO map_reader;


--
-- Name: SEQUENCE research_labs_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.research_labs_id_seq TO rp_engine;


--
-- Name: TABLE research_projects; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.research_projects TO rp_engine;
GRANT SELECT ON TABLE maya_rp.research_projects TO map_reader;


--
-- Name: SEQUENCE research_projects_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.research_projects_id_seq TO rp_engine;


--
-- Name: TABLE research_queue; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.research_queue TO rp_engine;
GRANT SELECT ON TABLE maya_rp.research_queue TO map_reader;


--
-- Name: SEQUENCE research_queue_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.research_queue_id_seq TO rp_engine;


--
-- Name: TABLE resource_inventory; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.resource_inventory TO rp_engine;
GRANT SELECT ON TABLE maya_rp.resource_inventory TO map_reader;


--
-- Name: TABLE strategic_resources; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.strategic_resources TO rp_engine;
GRANT SELECT ON TABLE maya_rp.strategic_resources TO map_reader;


--
-- Name: TABLE territory_resources; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.territory_resources TO rp_engine;
GRANT SELECT ON TABLE maya_rp.territory_resources TO map_reader;


--
-- Name: TABLE resource_overview; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.resource_overview TO rp_engine;
GRANT SELECT ON TABLE maya_rp.resource_overview TO map_reader;


--
-- Name: TABLE resource_production; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.resource_production TO rp_engine;
GRANT SELECT ON TABLE maya_rp.resource_production TO map_reader;


--
-- Name: TABLE resources; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.resources TO rp_engine;
GRANT SELECT ON TABLE maya_rp.resources TO map_reader;


--
-- Name: TABLE roll_history; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.roll_history TO rp_engine;
GRANT SELECT ON TABLE maya_rp.roll_history TO map_reader;


--
-- Name: SEQUENCE roll_history_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.roll_history_id_seq TO rp_engine;


--
-- Name: TABLE roll_outcome_tiers; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.roll_outcome_tiers TO rp_engine;
GRANT SELECT ON TABLE maya_rp.roll_outcome_tiers TO map_reader;


--
-- Name: SEQUENCE roll_outcome_tiers_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.roll_outcome_tiers_id_seq TO rp_engine;


--
-- Name: TABLE roll_state; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.roll_state TO map_reader;


--
-- Name: TABLE roll_types; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.roll_types TO rp_engine;
GRANT SELECT ON TABLE maya_rp.roll_types TO map_reader;


--
-- Name: SEQUENCE roll_types_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.roll_types_id_seq TO rp_engine;


--
-- Name: TABLE romance_arcs; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.romance_arcs TO rp_engine;
GRANT SELECT ON TABLE maya_rp.romance_arcs TO map_reader;


--
-- Name: SEQUENCE romance_arcs_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.romance_arcs_id_seq TO rp_engine;


--
-- Name: TABLE romance_tiers; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.romance_tiers TO rp_engine;
GRANT SELECT ON TABLE maya_rp.romance_tiers TO map_reader;


--
-- Name: SEQUENCE romance_tiers_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.romance_tiers_id_seq TO rp_engine;


--
-- Name: TABLE royal_accounts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.royal_accounts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.royal_accounts TO map_reader;


--
-- Name: SEQUENCE royal_accounts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.royal_accounts_id_seq TO rp_engine;


--
-- Name: TABLE royal_offspring; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.royal_offspring TO rp_engine;
GRANT SELECT ON TABLE maya_rp.royal_offspring TO map_reader;


--
-- Name: SEQUENCE royal_offspring_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.royal_offspring_id_seq TO rp_engine;


--
-- Name: TABLE savepoints; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.savepoints TO rp_engine;
GRANT SELECT ON TABLE maya_rp.savepoints TO map_reader;


--
-- Name: SEQUENCE savepoints_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.savepoints_id_seq TO rp_engine;


--
-- Name: TABLE scene_stack; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.scene_stack TO rp_engine;
GRANT SELECT ON TABLE maya_rp.scene_stack TO map_reader;


--
-- Name: SEQUENCE scene_stack_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.scene_stack_id_seq TO rp_engine;


--
-- Name: TABLE science_missions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.science_missions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.science_missions TO map_reader;


--
-- Name: SEQUENCE science_missions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.science_missions_id_seq TO rp_engine;


--
-- Name: TABLE scientific_theories; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.scientific_theories TO rp_engine;
GRANT SELECT ON TABLE maya_rp.scientific_theories TO map_reader;


--
-- Name: SEQUENCE scientific_theories_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.scientific_theories_id_seq TO rp_engine;


--
-- Name: TABLE scientist_assignments; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.scientist_assignments TO rp_engine;
GRANT SELECT ON TABLE maya_rp.scientist_assignments TO map_reader;


--
-- Name: SEQUENCE scientist_assignments_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.scientist_assignments_id_seq TO rp_engine;


--
-- Name: TABLE score_history; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.score_history TO rp_engine;
GRANT SELECT ON TABLE maya_rp.score_history TO map_reader;


--
-- Name: SEQUENCE score_history_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.score_history_id_seq TO rp_engine;


--
-- Name: TABLE secrets; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.secrets TO rp_engine;
GRANT SELECT ON TABLE maya_rp.secrets TO map_reader;


--
-- Name: SEQUENCE secrets_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.secrets_id_seq TO rp_engine;


--
-- Name: TABLE sector_connections; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.sector_connections TO rp_engine;
GRANT SELECT ON TABLE maya_rp.sector_connections TO map_reader;


--
-- Name: SEQUENCE sector_connections_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.sector_connections_id_seq TO rp_engine;


--
-- Name: TABLE sector_resources; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.sector_resources TO rp_engine;
GRANT SELECT ON TABLE maya_rp.sector_resources TO map_reader;


--
-- Name: SEQUENCE sector_resources_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.sector_resources_id_seq TO rp_engine;


--
-- Name: TABLE sector_visibility; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.sector_visibility TO rp_engine;
GRANT SELECT ON TABLE maya_rp.sector_visibility TO map_reader;


--
-- Name: SEQUENCE sector_visibility_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.sector_visibility_id_seq TO rp_engine;


--
-- Name: SEQUENCE sectors_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.sectors_id_seq TO rp_engine;


--
-- Name: TABLE sessions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.sessions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.sessions TO map_reader;


--
-- Name: SEQUENCE sessions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.sessions_id_seq TO rp_engine;


--
-- Name: TABLE ship_armaments; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ship_armaments TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ship_armaments TO map_reader;


--
-- Name: SEQUENCE ship_armaments_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ship_armaments_id_seq TO rp_engine;


--
-- Name: TABLE ship_classes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ship_classes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ship_classes TO map_reader;


--
-- Name: SEQUENCE ship_classes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ship_classes_id_seq TO rp_engine;


--
-- Name: TABLE ship_modules; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ship_modules TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ship_modules TO map_reader;


--
-- Name: SEQUENCE ship_modules_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ship_modules_id_seq TO rp_engine;


--
-- Name: TABLE ship_roles; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ship_roles TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ship_roles TO map_reader;


--
-- Name: SEQUENCE ship_roles_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ship_roles_id_seq TO rp_engine;


--
-- Name: TABLE ship_sub_classes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ship_sub_classes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ship_sub_classes TO map_reader;


--
-- Name: SEQUENCE ship_sub_classes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ship_sub_classes_id_seq TO rp_engine;


--
-- Name: TABLE ship_tech_bonuses; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ship_tech_bonuses TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ship_tech_bonuses TO map_reader;


--
-- Name: SEQUENCE ship_tech_bonuses_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ship_tech_bonuses_id_seq TO rp_engine;


--
-- Name: TABLE ship_types; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ship_types TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ship_types TO map_reader;


--
-- Name: TABLE ships; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.ships TO rp_engine;
GRANT SELECT ON TABLE maya_rp.ships TO map_reader;


--
-- Name: SEQUENCE ships_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.ships_id_seq TO rp_engine;


--
-- Name: TABLE sieges; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.sieges TO rp_engine;
GRANT SELECT ON TABLE maya_rp.sieges TO map_reader;


--
-- Name: SEQUENCE sieges_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.sieges_id_seq TO rp_engine;


--
-- Name: TABLE slave_births; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.slave_births TO rp_engine;
GRANT SELECT ON TABLE maya_rp.slave_births TO map_reader;


--
-- Name: SEQUENCE slave_births_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.slave_births_id_seq TO rp_engine;


--
-- Name: TABLE slave_market; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.slave_market TO rp_engine;
GRANT SELECT ON TABLE maya_rp.slave_market TO map_reader;


--
-- Name: SEQUENCE slave_market_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.slave_market_id_seq TO rp_engine;


--
-- Name: TABLE slaves; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.slaves TO rp_engine;
GRANT SELECT ON TABLE maya_rp.slaves TO map_reader;


--
-- Name: TABLE slave_overview; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.slave_overview TO rp_engine;
GRANT SELECT ON TABLE maya_rp.slave_overview TO map_reader;


--
-- Name: TABLE slave_revolts; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.slave_revolts TO rp_engine;
GRANT SELECT ON TABLE maya_rp.slave_revolts TO map_reader;


--
-- Name: SEQUENCE slave_revolts_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.slave_revolts_id_seq TO rp_engine;


--
-- Name: TABLE slave_training; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.slave_training TO rp_engine;
GRANT SELECT ON TABLE maya_rp.slave_training TO map_reader;


--
-- Name: SEQUENCE slave_training_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.slave_training_id_seq TO rp_engine;


--
-- Name: SEQUENCE slaves_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.slaves_id_seq TO rp_engine;


--
-- Name: TABLE social_events; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.social_events TO rp_engine;
GRANT SELECT ON TABLE maya_rp.social_events TO map_reader;


--
-- Name: SEQUENCE social_events_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.social_events_id_seq TO rp_engine;


--
-- Name: TABLE social_templates; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.social_templates TO rp_engine;
GRANT SELECT ON TABLE maya_rp.social_templates TO map_reader;


--
-- Name: SEQUENCE social_templates_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.social_templates_id_seq TO rp_engine;


--
-- Name: TABLE space_animals; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.space_animals TO rp_engine;
GRANT SELECT ON TABLE maya_rp.space_animals TO map_reader;


--
-- Name: SEQUENCE space_animals_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.space_animals_id_seq TO rp_engine;


--
-- Name: TABLE space_anomalies; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.space_anomalies TO rp_engine;
GRANT SELECT ON TABLE maya_rp.space_anomalies TO map_reader;


--
-- Name: SEQUENCE space_anomalies_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.space_anomalies_id_seq TO rp_engine;


--
-- Name: TABLE space_lanes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.space_lanes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.space_lanes TO map_reader;


--
-- Name: SEQUENCE space_lanes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.space_lanes_id_seq TO rp_engine;


--
-- Name: TABLE species_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.species_catalog TO rp_engine;
GRANT SELECT ON TABLE maya_rp.species_catalog TO map_reader;


--
-- Name: SEQUENCE species_catalog_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.species_catalog_id_seq TO rp_engine;


--
-- Name: TABLE spy_networks; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.spy_networks TO rp_engine;
GRANT SELECT ON TABLE maya_rp.spy_networks TO map_reader;


--
-- Name: SEQUENCE spy_networks_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.spy_networks_id_seq TO rp_engine;


--
-- Name: TABLE standing_orders; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.standing_orders TO rp_engine;
GRANT SELECT ON TABLE maya_rp.standing_orders TO map_reader;


--
-- Name: SEQUENCE standing_orders_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.standing_orders_id_seq TO rp_engine;


--
-- Name: TABLE state; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.state TO rp_engine;
GRANT SELECT ON TABLE maya_rp.state TO map_reader;


--
-- Name: TABLE state_snapshots; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.state_snapshots TO rp_engine;
GRANT SELECT ON TABLE maya_rp.state_snapshots TO map_reader;


--
-- Name: SEQUENCE state_snapshots_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.state_snapshots_id_seq TO rp_engine;


--
-- Name: TABLE stealth_unit_types; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.stealth_unit_types TO rp_engine;
GRANT SELECT ON TABLE maya_rp.stealth_unit_types TO map_reader;


--
-- Name: SEQUENCE stealth_unit_types_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.stealth_unit_types_id_seq TO rp_engine;


--
-- Name: TABLE stealth_units; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.stealth_units TO rp_engine;
GRANT SELECT ON TABLE maya_rp.stealth_units TO map_reader;


--
-- Name: SEQUENCE stealth_units_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.stealth_units_id_seq TO rp_engine;


--
-- Name: TABLE stock_prices; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.stock_prices TO rp_engine;
GRANT SELECT ON TABLE maya_rp.stock_prices TO map_reader;


--
-- Name: TABLE story_arcs; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.story_arcs TO rp_engine;
GRANT SELECT ON TABLE maya_rp.story_arcs TO map_reader;


--
-- Name: SEQUENCE story_arcs_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.story_arcs_id_seq TO rp_engine;


--
-- Name: TABLE story_checkpoints; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.story_checkpoints TO rp_engine;
GRANT SELECT ON TABLE maya_rp.story_checkpoints TO map_reader;


--
-- Name: SEQUENCE story_checkpoints_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.story_checkpoints_id_seq TO rp_engine;


--
-- Name: TABLE story_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.story_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.story_log TO map_reader;


--
-- Name: SEQUENCE story_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.story_log_id_seq TO rp_engine;


--
-- Name: SEQUENCE strategic_resources_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.strategic_resources_id_seq TO rp_engine;


--
-- Name: TABLE stream_templates; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.stream_templates TO rp_engine;
GRANT SELECT ON TABLE maya_rp.stream_templates TO map_reader;


--
-- Name: SEQUENCE stream_templates_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.stream_templates_id_seq TO rp_engine;


--
-- Name: TABLE supply_depots; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.supply_depots TO rp_engine;
GRANT SELECT ON TABLE maya_rp.supply_depots TO map_reader;


--
-- Name: SEQUENCE supply_depots_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.supply_depots_id_seq TO rp_engine;


--
-- Name: TABLE supply_lines; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.supply_lines TO rp_engine;
GRANT SELECT ON TABLE maya_rp.supply_lines TO map_reader;


--
-- Name: SEQUENCE supply_lines_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.supply_lines_id_seq TO rp_engine;


--
-- Name: TABLE tactical_states; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.tactical_states TO rp_engine;
GRANT SELECT ON TABLE maya_rp.tactical_states TO map_reader;


--
-- Name: SEQUENCE tactical_states_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.tactical_states_id_seq TO rp_engine;


--
-- Name: TABLE tactics_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.tactics_catalog TO rp_engine;
GRANT SELECT ON TABLE maya_rp.tactics_catalog TO map_reader;


--
-- Name: SEQUENCE tactics_catalog_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.tactics_catalog_id_seq TO rp_engine;


--
-- Name: TABLE talent_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.talent_catalog TO rp_engine;
GRANT SELECT ON TABLE maya_rp.talent_catalog TO map_reader;


--
-- Name: SEQUENCE talent_catalog_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.talent_catalog_id_seq TO rp_engine;


--
-- Name: TABLE task_routes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.task_routes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.task_routes TO map_reader;


--
-- Name: SEQUENCE task_routes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.task_routes_id_seq TO rp_engine;


--
-- Name: TABLE tax_history; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.tax_history TO rp_engine;
GRANT SELECT ON TABLE maya_rp.tax_history TO map_reader;


--
-- Name: SEQUENCE tax_history_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.tax_history_id_seq TO rp_engine;


--
-- Name: TABLE tech_tree; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.tech_tree TO rp_engine;
GRANT SELECT ON TABLE maya_rp.tech_tree TO map_reader;


--
-- Name: TABLE technologies; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.technologies TO rp_engine;
GRANT SELECT ON TABLE maya_rp.technologies TO map_reader;


--
-- Name: SEQUENCE technologies_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.technologies_id_seq TO rp_engine;


--
-- Name: TABLE tension_thresholds; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.tension_thresholds TO rp_engine;
GRANT SELECT ON TABLE maya_rp.tension_thresholds TO map_reader;


--
-- Name: SEQUENCE tension_thresholds_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.tension_thresholds_id_seq TO rp_engine;


--
-- Name: TABLE terraforming_projects; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.terraforming_projects TO rp_engine;
GRANT SELECT ON TABLE maya_rp.terraforming_projects TO map_reader;


--
-- Name: SEQUENCE terraforming_projects_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.terraforming_projects_id_seq TO rp_engine;


--
-- Name: SEQUENCE territory_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.territory_id_seq TO rp_engine;


--
-- Name: TABLE territory_modifiers; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.territory_modifiers TO rp_engine;
GRANT SELECT ON TABLE maya_rp.territory_modifiers TO map_reader;


--
-- Name: SEQUENCE territory_modifiers_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.territory_modifiers_id_seq TO rp_engine;


--
-- Name: SEQUENCE territory_resources_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.territory_resources_id_seq TO rp_engine;


--
-- Name: TABLE theme_state; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.theme_state TO rp_engine;
GRANT SELECT ON TABLE maya_rp.theme_state TO map_reader;


--
-- Name: TABLE tick_summaries; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.tick_summaries TO rp_engine;
GRANT SELECT ON TABLE maya_rp.tick_summaries TO map_reader;


--
-- Name: SEQUENCE tick_summaries_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.tick_summaries_id_seq TO rp_engine;


--
-- Name: TABLE time_skip_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.time_skip_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.time_skip_log TO map_reader;


--
-- Name: SEQUENCE time_skip_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.time_skip_log_id_seq TO rp_engine;


--
-- Name: TABLE trade_log; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.trade_log TO rp_engine;
GRANT SELECT ON TABLE maya_rp.trade_log TO map_reader;


--
-- Name: SEQUENCE trade_log_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.trade_log_id_seq TO rp_engine;


--
-- Name: TABLE trade_routes; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.trade_routes TO rp_engine;
GRANT SELECT ON TABLE maya_rp.trade_routes TO map_reader;


--
-- Name: SEQUENCE trade_routes_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.trade_routes_id_seq TO rp_engine;


--
-- Name: TABLE training_programs; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.training_programs TO rp_engine;
GRANT SELECT ON TABLE maya_rp.training_programs TO map_reader;


--
-- Name: SEQUENCE training_programs_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.training_programs_id_seq TO rp_engine;


--
-- Name: TABLE trait_assignments; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.trait_assignments TO rp_engine;
GRANT SELECT ON TABLE maya_rp.trait_assignments TO map_reader;


--
-- Name: SEQUENCE trait_assignments_assignment_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.trait_assignments_assignment_id_seq TO rp_engine;


--
-- Name: TABLE trait_catalog; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.trait_catalog TO rp_engine;
GRANT SELECT ON TABLE maya_rp.trait_catalog TO map_reader;


--
-- Name: SEQUENCE trait_catalog_trait_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.trait_catalog_trait_id_seq TO rp_engine;


--
-- Name: TABLE transport_missions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.transport_missions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.transport_missions TO map_reader;


--
-- Name: SEQUENCE transport_missions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.transport_missions_id_seq TO rp_engine;


--
-- Name: SEQUENCE treaties_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.treaties_id_seq TO rp_engine;


--
-- Name: TABLE unified_dashboard; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.unified_dashboard TO rp_engine;
GRANT SELECT ON TABLE maya_rp.unified_dashboard TO map_reader;


--
-- Name: TABLE university_campuses; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.university_campuses TO rp_engine;
GRANT SELECT ON TABLE maya_rp.university_campuses TO map_reader;


--
-- Name: SEQUENCE university_campuses_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.university_campuses_id_seq TO rp_engine;


--
-- Name: TABLE victory_tracking; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.victory_tracking TO rp_engine;
GRANT SELECT ON TABLE maya_rp.victory_tracking TO map_reader;


--
-- Name: SEQUENCE victory_tracking_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.victory_tracking_id_seq TO rp_engine;


--
-- Name: TABLE voyages; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT SELECT ON TABLE maya_rp.voyages TO map_reader;


--
-- Name: TABLE war_exhaustion_effects; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.war_exhaustion_effects TO rp_engine;
GRANT SELECT ON TABLE maya_rp.war_exhaustion_effects TO map_reader;


--
-- Name: SEQUENCE war_exhaustion_effects_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.war_exhaustion_effects_id_seq TO rp_engine;


--
-- Name: TABLE wars; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.wars TO rp_engine;
GRANT SELECT ON TABLE maya_rp.wars TO map_reader;


--
-- Name: SEQUENCE wars_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.wars_id_seq TO rp_engine;


--
-- Name: TABLE weapon_blueprints; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.weapon_blueprints TO rp_engine;
GRANT SELECT ON TABLE maya_rp.weapon_blueprints TO map_reader;


--
-- Name: SEQUENCE weapon_blueprints_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.weapon_blueprints_id_seq TO rp_engine;


--
-- Name: TABLE weapon_kinds; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.weapon_kinds TO rp_engine;
GRANT SELECT ON TABLE maya_rp.weapon_kinds TO map_reader;


--
-- Name: TABLE weapon_upgrades; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.weapon_upgrades TO rp_engine;
GRANT SELECT ON TABLE maya_rp.weapon_upgrades TO map_reader;


--
-- Name: SEQUENCE weapon_upgrades_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.weapon_upgrades_id_seq TO rp_engine;


--
-- Name: TABLE weapons; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.weapons TO rp_engine;
GRANT SELECT ON TABLE maya_rp.weapons TO map_reader;


--
-- Name: SEQUENCE weapons_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.weapons_id_seq TO rp_engine;


--
-- Name: TABLE wiki_articles; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.wiki_articles TO rp_engine;
GRANT SELECT ON TABLE maya_rp.wiki_articles TO map_reader;


--
-- Name: SEQUENCE wiki_articles_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.wiki_articles_id_seq TO rp_engine;


--
-- Name: TABLE world_reactions; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.world_reactions TO rp_engine;
GRANT SELECT ON TABLE maya_rp.world_reactions TO map_reader;


--
-- Name: SEQUENCE world_reactions_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.world_reactions_id_seq TO rp_engine;


--
-- Name: TABLE wreck_inventory; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.wreck_inventory TO rp_engine;
GRANT SELECT ON TABLE maya_rp.wreck_inventory TO map_reader;


--
-- Name: SEQUENCE wreck_inventory_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.wreck_inventory_id_seq TO rp_engine;


--
-- Name: TABLE yard_capacity; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON TABLE maya_rp.yard_capacity TO rp_engine;
GRANT SELECT ON TABLE maya_rp.yard_capacity TO map_reader;


--
-- Name: SEQUENCE yard_capacity_id_seq; Type: ACL; Schema: maya_rp; Owner: -
--

GRANT ALL ON SEQUENCE maya_rp.yard_capacity_id_seq TO rp_engine;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: maya_rp; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE maya IN SCHEMA maya_rp GRANT ALL ON SEQUENCES TO rp_engine;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: maya_rp; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE maya IN SCHEMA maya_rp GRANT ALL ON TABLES TO rp_engine;
ALTER DEFAULT PRIVILEGES FOR ROLE maya IN SCHEMA maya_rp GRANT SELECT ON TABLES TO map_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict VP8UaTSvRMDL6ihCFXrHZu06P59CDSPHRfRJiyRfLYPPLhWkLaopgAPUYuqu79I

