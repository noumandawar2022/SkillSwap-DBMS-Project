-- ============================================================
-- SkillSwap - Notification Triggers
-- ============================================================

-- 1. Request Accepted -> Notify Requester
CREATE OR REPLACE TRIGGER trg_notif_request_accepted
AFTER UPDATE OF STATUS ON REQUESTS
FOR EACH ROW
WHEN (
    NEW.STATUS = 'ACCEPTED'
    AND OLD.STATUS <> 'ACCEPTED'
)
DECLARE
    v_skill_name VARCHAR2(100);
    v_offerer_id NUMBER;
BEGIN
    SELECT SKILL_NAME
    INTO v_skill_name
    FROM SKILLS
    WHERE SKILL_ID = :NEW.SKILL_ID;

    SELECT USER_ID
    INTO v_offerer_id
    FROM OFFERS
    WHERE OFFER_ID = :NEW.OFFER_ID;

    INSERT INTO NOTIFICATIONS (
        TO_USER_ID,
        FROM_USER_ID,
        NOTIFICATION_TYPE,
        CONTENT
    )
    VALUES (
        :NEW.USER_ID,
        v_offerer_id,
        'MATCH',
        'Your request for "' || v_skill_name || '" has been accepted.'
    );
END;
/
 
-- 2. Session Created -> Notify Both Users
CREATE OR REPLACE TRIGGER trg_notif_session_created
AFTER INSERT ON SESSIONS
FOR EACH ROW
DECLARE
    v_requester NUMBER;
    v_offerer   NUMBER;
BEGIN
    SELECT USER_ID
    INTO v_requester
    FROM REQUESTS
    WHERE REQUEST_ID = :NEW.REQUEST_ID;

    SELECT USER_ID
    INTO v_offerer
    FROM OFFERS
    WHERE OFFER_ID = :NEW.OFFER_ID;

    INSERT INTO NOTIFICATIONS (
        TO_USER_ID,
        FROM_USER_ID,
        NOTIFICATION_TYPE,
        CONTENT
    )
    VALUES (
        v_requester,
        v_offerer,
        'SESSION',
        'A session has been scheduled.'
    );

    INSERT INTO NOTIFICATIONS (
        TO_USER_ID,
        FROM_USER_ID,
        NOTIFICATION_TYPE,
        CONTENT
    )
    VALUES (
        v_offerer,
        v_requester,
        'SESSION',
        'A session has been scheduled.'
    );
END;
/
 
-- 3. Feedback Submitted -> Notify Offerer
CREATE OR REPLACE TRIGGER trg_notif_feedback_submitted
AFTER INSERT ON FEEDBACK
FOR EACH ROW
DECLARE
    v_requester NUMBER;
    v_offerer   NUMBER;
BEGIN
    SELECT r.USER_ID,
           o.USER_ID
    INTO v_requester,
         v_offerer
    FROM SESSIONS s
    JOIN REQUESTS r
      ON r.REQUEST_ID = s.REQUEST_ID
    JOIN OFFERS o
      ON o.OFFER_ID = s.OFFER_ID
    WHERE s.SESSION_ID = :NEW.SESSION_ID;

    INSERT INTO NOTIFICATIONS (
        TO_USER_ID,
        FROM_USER_ID,
        NOTIFICATION_TYPE,
        CONTENT
    )
    VALUES (
        v_offerer,
        v_requester,
        'FEEDBACK',
        'You received new feedback.'
    );
END;
/
 
-- 4. Endorsement Submitted -> Notify Endorsed User
CREATE OR REPLACE TRIGGER trg_notif_endorsement_submitted
AFTER INSERT ON ENDORSEMENTS
FOR EACH ROW
BEGIN
    INSERT INTO NOTIFICATIONS (
        TO_USER_ID,
        FROM_USER_ID,
        NOTIFICATION_TYPE,
        CONTENT
    )
    VALUES (
        :NEW.ENDORSED_USER_ID,
        :NEW.ENDORSED_BY_ID,
        'ENDORSEMENT',
        'You received a new endorsement.'
    );
END;
/
 
-- 5. New Message -> Notify Other Participant
CREATE OR REPLACE TRIGGER trg_notif_message
AFTER INSERT ON MESSAGES
FOR EACH ROW
DECLARE
    v_requester NUMBER;
    v_offerer   NUMBER;
    v_receiver  NUMBER;
BEGIN
    SELECT r.USER_ID,
           o.USER_ID
    INTO v_requester,
         v_offerer
    FROM SESSIONS s
    JOIN REQUESTS r
      ON r.REQUEST_ID = s.REQUEST_ID
    JOIN OFFERS o
      ON o.OFFER_ID = s.OFFER_ID
    WHERE s.SESSION_ID = :NEW.SESSION_ID;

    IF :NEW.SENDER_ID = v_requester THEN
        v_receiver := v_offerer;
    ELSE
        v_receiver := v_requester;
    END IF;

    INSERT INTO NOTIFICATIONS (
        TO_USER_ID,
        FROM_USER_ID,
        NOTIFICATION_TYPE,
        CONTENT
    )
    VALUES (
        v_receiver,
        :NEW.SENDER_ID,
        'MESSAGE',
        'You received a new message.'
    );
END;
/