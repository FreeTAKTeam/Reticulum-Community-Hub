use super::{
    DeserializeOwned, MissionCommandEnvelope, RchCore, RchCoreError, ReadSet,
    checklist_required_capability, decode_msgpack, normalize_hash, params_from_iter,
    required_capability,
};

impl ReadSet<'_> {
    pub(super) fn query<T: DeserializeOwned>(
        &mut self,
        sql: &str,
        values: &[&str],
    ) -> Result<Vec<T>, RchCoreError> {
        let mut statement = self.connection.prepare(sql)?;
        let mut rows = statement.query(params_from_iter(values.iter()))?;
        let mut records = Vec::new();
        while let Some(row) = rows.next()? {
            let payload: Vec<u8> = row.get(0)?;
            self.rows += 1;
            self.bytes = self.bytes.saturating_add(payload.len());
            records.push(decode_msgpack(&payload)?);
        }
        Ok(records)
    }
    pub fn authorization(
        &mut self,
        command: &MissionCommandEnvelope,
        core: &RchCore,
    ) -> Result<(), RchCoreError> {
        let mut scopes = core.candidate_mission_uids(command);
        scopes.extend(core.candidate_checklist_mission_uid(command));
        scopes.sort();
        scopes.dedup();
        let capability = if command.command_type.starts_with("checklist.") {
            checklist_required_capability(&command.command_type)
        } else {
            required_capability(&command.command_type)
        };
        if let Some(operation) = capability {
            for (subject_type, subject_id) in
                core.subject_refs_for_identity(&command.source.rns_identity)
            {
                let rights=self.query("SELECT payload FROM rch_subject_operation_rights WHERE subject_type=?1 AND subject_id=?2 AND scope_type='global' AND operation=?3",&[&subject_type,&subject_id,operation])?;
                for record in rights {
                    if !self.snapshot.subject_operation_rights.contains(&record) {
                        self.snapshot.subject_operation_rights.push(record);
                    }
                }
                for scope in &scopes {
                    let rights=self.query("SELECT payload FROM rch_subject_operation_rights WHERE subject_type=?1 AND subject_id=?2 AND scope_type='mission' AND scope_id=?3 AND operation=?4",&[&subject_type,&subject_id,scope,operation])?;
                    for record in rights {
                        if !self.snapshot.subject_operation_rights.contains(&record) {
                            self.snapshot.subject_operation_rights.push(record);
                        }
                    }
                    let access=self.query("SELECT payload FROM rch_mission_access_assignments WHERE subject_type=?1 AND subject_id=?2 AND mission_uid=?3",&[&subject_type,&subject_id,scope])?;
                    for record in access {
                        if !self.snapshot.mission_access_assignments.contains(&record) {
                            self.snapshot.mission_access_assignments.push(record);
                        }
                    }
                }
            }
        }
        Ok(())
    }

    /// Event routing is an explicit post-mutation dependency, limited to the emitted mission/team.
    pub fn recipients(
        &mut self,
        mission: Option<&str>,
        team: Option<&str>,
    ) -> Result<(), RchCoreError> {
        let r = self;
        select!(r, teams, "rch_teams", "uid", team);
        if team.is_none() {
            select!(
                r,
                mission_team_links,
                "rch_mission_team_links",
                "mission_uid",
                mission
            );
        }
        for link in r.snapshot.mission_team_links.clone() {
            select!(r, teams, "rch_teams", "uid", Some(link.team_uid.as_str()));
        }
        for team in r.snapshot.teams.clone() {
            select!(
                r,
                team_members,
                "rch_team_members",
                "team_uid",
                Some(team.uid.as_str())
            );
        }
        for member in r.snapshot.team_members.clone() {
            select!(
                r,
                team_member_client_links,
                "rch_team_member_client_links",
                "team_member_uid",
                Some(member.uid.as_str())
            );
            for identity in
                std::iter::once(&member.rns_identity).chain(member.client_identities.iter())
            {
                select!(
                    r,
                    identity_states,
                    "rch_identity_states",
                    "identity",
                    normalize_hash(Some(identity)).as_deref()
                );
                select!(
                    r,
                    identity_announces,
                    "rch_identity_announces",
                    "normalized_destination_hash",
                    normalize_hash(Some(identity)).as_deref()
                );
                select!(
                    r,
                    identity_announces,
                    "rch_identity_announces",
                    "normalized_announced_identity_hash",
                    normalize_hash(Some(identity)).as_deref()
                );
            }
        }
        for announce in r.snapshot.identity_announces.clone() {
            select!(
                r,
                identity_rem_modes,
                "rch_identity_rem_modes",
                "identity",
                normalize_hash(Some(&announce.destination_hash)).as_deref()
            );
            select!(
                r,
                identity_rem_modes,
                "rch_identity_rem_modes",
                "identity",
                announce
                    .announced_identity_hash
                    .as_deref()
                    .and_then(|v| normalize_hash(Some(v)))
            );
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                normalize_hash(Some(&announce.destination_hash)).as_deref()
            );
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                announce
                    .announced_identity_hash
                    .as_deref()
                    .and_then(|v| normalize_hash(Some(v)))
            );
        }
        for link in r.snapshot.team_member_client_links.clone() {
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                normalize_hash(Some(&link.client_identity)).as_deref()
            );
        }
        Ok(())
    }
    pub fn collector(&mut self, topic: Option<&str>) -> Result<(), RchCoreError> {
        let r = self;
        select!(r, topics, "rch_topics", "topic_id", topic);
        select!(r, subscribers, "rch_subscribers", "topic_id", topic);
        // The collector returns a global snapshot without topic; all block policies are relevant.
        all!(r, identity_states, "rch_identity_states");
        Ok(())
    }

    pub fn source(&mut self, source: &str) -> Result<(), RchCoreError> {
        let r = self;
        let source = normalize_hash(Some(source));
        select!(
            r,
            identity_states,
            "rch_identity_states",
            "identity",
            source.as_deref()
        );
        // Every inbound sender refreshes its own roster row.
        select!(
            r,
            clients,
            "rch_clients",
            "identity_normalized",
            source.as_deref()
        );
        Ok(())
    }

    /// Chat routing reads its actual roster/topic recipient set, never registry history.
    pub fn routing(&mut self, source: &str, topic: &str) -> Result<(), RchCoreError> {
        let r = self;
        let source = normalize_hash(Some(source));
        select!(
            r,
            clients,
            "rch_clients",
            "identity_normalized",
            source.as_deref()
        );
        select!(
            r,
            identity_states,
            "rch_identity_states",
            "identity",
            source.as_deref()
        );
        // Relays label the sender with its announced display name.
        select!(
            r,
            identity_announces,
            "rch_identity_announces",
            "normalized_destination_hash",
            source.as_deref()
        );
        select!(r, topics, "rch_topics", "topic_id", Some(topic));
        select!(r, subscribers, "rch_subscribers", "topic_id", Some(topic));
        if topic == "direct" {
            all!(r, clients, "rch_clients");
        }
        for client in r.snapshot.clients.clone() {
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                Some(client.identity.as_str())
            );
        }
        for subscriber in r.snapshot.subscribers.clone() {
            select!(
                r,
                clients,
                "rch_clients",
                "identity_normalized",
                Some(subscriber.node_id.as_str())
            );
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                Some(subscriber.node_id.as_str())
            );
        }
        Ok(())
    }
}
