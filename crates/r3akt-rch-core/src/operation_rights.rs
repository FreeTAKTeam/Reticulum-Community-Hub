use super::{
    RchCore, RchCoreError, SubjectOperationRight, Uuid, normalize_scope_id, normalize_scope_type,
    normalize_subject_id, normalize_subject_type, required_non_empty,
};

pub(super) type OperationRightKey = (String, String, String, String, String);

// Both resident domain commands and keyed durable writes use this validation.
pub(super) fn operation_right_key(
    subject_type: &str,
    subject_id: &str,
    operation: &str,
    scope_type: &str,
    scope_id: &str,
) -> Result<OperationRightKey, RchCoreError> {
    let subject_type = normalize_subject_type(subject_type)?;
    let subject_id = normalize_subject_id(&subject_type, subject_id)?;
    let operation = required_non_empty(operation, "operation")?;
    let scope_type = normalize_scope_type(scope_type)?;
    let scope_id = normalize_scope_id(&scope_type, scope_id);
    Ok((subject_type, subject_id, operation, scope_type, scope_id))
}

pub(super) fn operation_right_record(
    key: &OperationRightKey,
    previous: Option<&SubjectOperationRight>,
    granted: bool,
) -> SubjectOperationRight {
    SubjectOperationRight {
        grant_uid: previous.map_or_else(
            || Uuid::new_v4().simple().to_string(),
            |record| record.grant_uid.clone(),
        ),
        subject_type: key.0.clone(),
        subject_id: key.1.clone(),
        operation: key.2.clone(),
        scope_type: key.3.clone(),
        scope_id: key.4.clone(),
        granted,
    }
}

impl RchCore {
    pub fn grant_operation_right(
        &mut self,
        subject_type: impl AsRef<str>,
        subject_id: impl AsRef<str>,
        operation: impl AsRef<str>,
        scope_type: impl AsRef<str>,
        scope_id: impl AsRef<str>,
    ) -> Result<SubjectOperationRight, RchCoreError> {
        self.upsert_operation_right(
            subject_type,
            subject_id,
            operation,
            scope_type,
            scope_id,
            true,
        )
    }

    pub fn revoke_operation_right(
        &mut self,
        subject_type: impl AsRef<str>,
        subject_id: impl AsRef<str>,
        operation: impl AsRef<str>,
        scope_type: impl AsRef<str>,
        scope_id: impl AsRef<str>,
    ) -> Result<SubjectOperationRight, RchCoreError> {
        self.upsert_operation_right(
            subject_type,
            subject_id,
            operation,
            scope_type,
            scope_id,
            false,
        )
    }

    fn upsert_operation_right(
        &mut self,
        subject_type: impl AsRef<str>,
        subject_id: impl AsRef<str>,
        operation: impl AsRef<str>,
        scope_type: impl AsRef<str>,
        scope_id: impl AsRef<str>,
        granted: bool,
    ) -> Result<SubjectOperationRight, RchCoreError> {
        let key = operation_right_key(
            subject_type.as_ref(),
            subject_id.as_ref(),
            operation.as_ref(),
            scope_type.as_ref(),
            scope_id.as_ref(),
        )?;
        let record = operation_right_record(&key, self.subject_operation_rights.get(&key), granted);
        self.subject_operation_rights.insert(key, record.clone());
        Ok(record)
    }
}
