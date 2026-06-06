-- ============================================================
-- SkillSwap - Oracle PL/SQL Triggers (Business Rules)
-- Final version matched to the finalized schema
-- ============================================================

-- ============================================================
-- 1. Prevent duplicate active requests
--    Same user cannot have more than one PENDING/ACCEPTED
--    request for the same skill.
--    Uses a compound trigger to avoid mutating-table issues.
-- ============================================================
CREATE OR REPLACE TRIGGER trg_no_duplicate_requests
FOR INSERT OR UPDATE OF USER_ID, SKILL_ID, STATUS ON REQUESTS
COMPOUND TRIGGER

    TYPE t_request_rec IS RECORD (
        user_id  REQUESTS.USER_ID%TYPE,
        skill_id REQUESTS.SKILL_ID%TYPE
    );

    TYPE t_request_tab IS TABLE OF t_request_rec INDEX BY PLS_INTEGER;

    g_rows   t_request_tab;
    g_index  PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        IF :NEW.STATUS IN ('PENDING', 'ACCEPTED') THEN
            g_index := g_index + 1;
            g_rows(g_index).user_id  := :NEW.USER_ID;
            g_rows(g_index).skill_id := :NEW.SKILL_ID;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
        v_count NUMBER;
    BEGIN
        IF g_index > 0 THEN
            FOR i IN 1 .. g_index LOOP
                SELECT COUNT(*)
                INTO v_count
                FROM REQUESTS
                WHERE USER_ID = g_rows(i).user_id
                  AND SKILL_ID = g_rows(i).skill_id
                  AND STATUS IN ('PENDING', 'ACCEPTED');

                IF v_count > 1 THEN
                    RAISE_APPLICATION_ERROR(
                        -20001,
                        'Duplicate active request for this skill is not allowed.'
                    );
                END IF;
            END LOOP;
        END IF;
    END AFTER STATEMENT;

END trg_no_duplicate_requests;
/
 
-- ============================================================
-- 2. Prevent self-requesting
--    A user cannot request their own offer.
-- ============================================================
CREATE OR REPLACE TRIGGER trg_no_self_request
BEFORE INSERT OR UPDATE OF USER_ID, OFFER_ID ON REQUESTS
FOR EACH ROW
DECLARE
    v_offer_owner NUMBER;
BEGIN
    SELECT USER_ID
    INTO v_offer_owner
    FROM OFFERS
    WHERE OFFER_ID = :NEW.OFFER_ID;

    IF :NEW.USER_ID = v_offer_owner THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'A user cannot request their own offer.'
        );
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Invalid offer selected.'
        );
END trg_no_self_request;
/
 
-- ============================================================
-- 3. Validate that selected availability belongs to the offer
-- ============================================================
CREATE OR REPLACE TRIGGER trg_validate_availability
BEFORE INSERT OR UPDATE OF OFFER_ID, SELECTED_AVAILABILITY_ID ON REQUESTS
FOR EACH ROW
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM AVAILABILITY
    WHERE AVAILABILITY_ID = :NEW.SELECTED_AVAILABILITY_ID
      AND OFFER_ID = :NEW.OFFER_ID;

    IF v_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Selected availability does not belong to the chosen offer.'
        );
    END IF;
END trg_validate_availability;
/
 
-- ============================================================
-- 4. Auto-complete session when both users confirm
-- ============================================================
CREATE OR REPLACE TRIGGER trg_auto_complete_session
BEFORE INSERT OR UPDATE OF REQUESTER_CONFIRMED, OFFERER_CONFIRMED, STATUS ON SESSIONS
FOR EACH ROW
BEGIN
    IF :NEW.REQUESTER_CONFIRMED = 1
       AND :NEW.OFFERER_CONFIRMED = 1
    THEN
        :NEW.STATUS := 'COMPLETED';
        :NEW.COMPLETED_AT := NVL(:NEW.COMPLETED_AT, SYSDATE);
    END IF;
END trg_auto_complete_session;
/
 
-- ============================================================
-- 5. Prevent feedback before session completion
-- ============================================================
CREATE OR REPLACE TRIGGER trg_no_feedback_before_complete
BEFORE INSERT ON FEEDBACK
FOR EACH ROW
DECLARE
    v_status VARCHAR2(10);
BEGIN
    SELECT STATUS
    INTO v_status
    FROM SESSIONS
    WHERE SESSION_ID = :NEW.SESSION_ID;

    IF v_status <> 'COMPLETED' THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Feedback can only be submitted after the session is completed.'
        );
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Invalid session for feedback.'
        );
END trg_no_feedback_before_complete;
/
 
-- ============================================================
-- 6. Prevent self-endorsement
--    Duplicate endorsements are already prevented by the
--    UNIQUE constraint on (ENDORSED_USER_ID, ENDORSED_BY_ID, SKILL_ID).
-- ============================================================
CREATE OR REPLACE TRIGGER trg_no_self_endorsement
BEFORE INSERT OR UPDATE OF ENDORSED_USER_ID, ENDORSED_BY_ID ON ENDORSEMENTS
FOR EACH ROW
BEGIN
    IF :NEW.ENDORSED_USER_ID = :NEW.ENDORSED_BY_ID THEN
        RAISE_APPLICATION_ERROR(
            -20005,
            'A user cannot endorse themselves.'
        );
    END IF;
END trg_no_self_endorsement;
/
 
-- ============================================================
-- 7. Prevent deleting offers with active sessions
-- ============================================================
CREATE OR REPLACE TRIGGER trg_prevent_offer_delete
BEFORE DELETE ON OFFERS
FOR EACH ROW
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM SESSIONS
    WHERE OFFER_ID = :OLD.OFFER_ID
      AND STATUS = 'SCHEDULED';

    IF v_count > 0 THEN
        RAISE_APPLICATION_ERROR(
            -20006,
            'Cannot delete an offer that has active scheduled sessions.'
        );
    END IF;
END trg_prevent_offer_delete;
/
 
-- ============================================================
-- 8. Prevent messaging outside an accepted session
--    Only participants in the session can send messages.
-- ============================================================
CREATE OR REPLACE TRIGGER trg_validate_message_session
BEFORE INSERT ON MESSAGES
FOR EACH ROW
DECLARE
    v_requester_id NUMBER;
    v_offerer_id   NUMBER;
    v_status       VARCHAR2(10);
BEGIN
    SELECT r.USER_ID, o.USER_ID, s.STATUS
    INTO v_requester_id, v_offerer_id, v_status
    FROM SESSIONS s
    JOIN REQUESTS r ON r.REQUEST_ID = s.REQUEST_ID
    JOIN OFFERS o   ON o.OFFER_ID = s.OFFER_ID
    WHERE s.SESSION_ID = :NEW.SESSION_ID;

    IF v_status NOT IN ('SCHEDULED', 'COMPLETED') THEN
        RAISE_APPLICATION_ERROR(
            -20007,
            'Messages are allowed only after a session has been accepted.'
        );
    END IF;

    IF :NEW.SENDER_ID NOT IN (v_requester_id, v_offerer_id) THEN
        RAISE_APPLICATION_ERROR(
            -20008,
            'Only session participants can send messages.'
        );
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20007,
            'Invalid session for message.'
        );
END trg_validate_message_session;
/