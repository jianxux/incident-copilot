-- Extended Schema: Incident Events, Postmortems, Tags, Services, On-Call, Costs, Collaboration
-- This migration adds tables that were previously only in-memory stores.

-- ==================== Incident Events / Timeline ====================
CREATE TABLE IF NOT EXISTS incident_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    actor TEXT,
    source TEXT,
    metadata JSONB DEFAULT '{}',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_events_incident_id ON incident_events(incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_events_tenant_id ON incident_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_incident_events_occurred_at ON incident_events(occurred_at);

-- ==================== Postmortems ====================
CREATE TABLE IF NOT EXISTS postmortems (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'in_review', 'approved', 'published')),
    service_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    executive_summary TEXT NOT NULL,
    timeline JSONB DEFAULT '[]',
    root_cause JSONB,
    impact JSONB,
    resolution_steps JSONB DEFAULT '[]',
    action_items JSONB DEFAULT '[]',
    lessons_learned JSONB DEFAULT '[]',
    what_went_well JSONB DEFAULT '[]',
    what_went_poorly JSONB DEFAULT '[]',
    lucky_factors JSONB DEFAULT '[]',
    related_incidents JSONB DEFAULT '[]',
    alert_url TEXT,
    dashboard_url TEXT,
    runbook_url TEXT,
    incident_started_at TIMESTAMPTZ,
    incident_resolved_at TIMESTAMPTZ,
    incident_duration_minutes INTEGER,
    ai_generated BOOLEAN DEFAULT TRUE,
    ai_model TEXT,
    ai_confidence FLOAT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_postmortems_incident_id ON postmortems(incident_id);
CREATE INDEX IF NOT EXISTS idx_postmortems_tenant_id ON postmortems(tenant_id);
CREATE INDEX IF NOT EXISTS idx_postmortems_status ON postmortems(status);

-- ==================== Tags ====================
CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT DEFAULT 'blue',
    parent_id UUID REFERENCES tags(id) ON DELETE SET NULL,
    is_system BOOLEAN DEFAULT FALSE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

CREATE INDEX IF NOT EXISTS idx_tags_tenant_id ON tags(tenant_id);

-- Join table: incidents <-> tags
CREATE TABLE IF NOT EXISTS incident_tags (
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    applied_by UUID REFERENCES users(id) ON DELETE SET NULL,
    auto_applied BOOLEAN DEFAULT FALSE,
    confidence FLOAT,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (incident_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_incident_tags_tag_id ON incident_tags(tag_id);

-- Auto-tag rules
CREATE TABLE IF NOT EXISTS auto_tag_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auto_tag_rules_tenant_id ON auto_tag_rules(tenant_id);

-- ==================== Services & Dependencies ====================
CREATE TABLE IF NOT EXISTS services (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    criticality TEXT DEFAULT 'medium',
    team TEXT,
    owner_email TEXT,
    repo_url TEXT,
    dashboard_url TEXT,
    runbook_url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

CREATE INDEX IF NOT EXISTS idx_services_tenant_id ON services(tenant_id);

CREATE TABLE IF NOT EXISTS service_dependencies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    upstream_service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    downstream_service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    dependency_type TEXT DEFAULT 'runtime',
    is_critical BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(upstream_service_id, downstream_service_id)
);

CREATE INDEX IF NOT EXISTS idx_service_deps_upstream ON service_dependencies(upstream_service_id);
CREATE INDEX IF NOT EXISTS idx_service_deps_downstream ON service_dependencies(downstream_service_id);

-- ==================== On-Call Schedules ====================
CREATE TABLE IF NOT EXISTS on_call_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    schedule_id TEXT NOT NULL,
    schedule_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    service_id UUID REFERENCES services(id) ON DELETE SET NULL,
    schedule_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, provider, schedule_id)
);

CREATE INDEX IF NOT EXISTS idx_on_call_schedules_tenant_id ON on_call_schedules(tenant_id);

CREATE TABLE IF NOT EXISTS on_call_persons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_record_id UUID NOT NULL REFERENCES on_call_schedules(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    avatar_url TEXT,
    slack_user_id TEXT,
    provider_user_id TEXT,
    position INTEGER DEFAULT 0,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_on_call_persons_schedule ON on_call_persons(schedule_record_id);

-- ==================== Cost Tracking ====================
CREATE TABLE IF NOT EXISTS cost_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    description TEXT,
    team TEXT,
    department TEXT,
    engineer_id TEXT,
    engineer_name TEXT,
    hours_spent FLOAT,
    hourly_rate NUMERIC(10,2),
    source TEXT DEFAULT 'manual',
    metadata JSONB DEFAULT '{}',
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cost_entries_tenant_id ON cost_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cost_entries_incident_id ON cost_entries(incident_id);

-- ==================== Collaboration: Comments ====================
CREATE TABLE IF NOT EXISTS incident_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    author_name TEXT NOT NULL,
    author_email TEXT,
    content TEXT NOT NULL,
    mentions JSONB DEFAULT '[]',
    parent_id UUID REFERENCES incident_comments(id) ON DELETE CASCADE,
    reactions JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    edited BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_comments_incident_id ON incident_comments(incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_comments_tenant_id ON incident_comments(tenant_id);

-- ==================== Collaboration: Watchers ====================
CREATE TABLE IF NOT EXISTS incident_watchers (
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (incident_id, user_id)
);

-- ==================== Insights ====================
CREATE TABLE IF NOT EXISTS insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    insight_type TEXT NOT NULL,
    severity TEXT DEFAULT 'info',
    title TEXT NOT NULL,
    description TEXT,
    service_name TEXT,
    data JSONB DEFAULT '{}',
    affected_incident_ids JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insights_tenant_id ON insights(tenant_id);
CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(insight_type);

-- ==================== Enable RLS on new tables ====================
ALTER TABLE incident_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE postmortems ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE auto_tag_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE services ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_dependencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE on_call_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE on_call_persons ENABLE ROW LEVEL SECURITY;
ALTER TABLE cost_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_watchers ENABLE ROW LEVEL SECURITY;
ALTER TABLE insights ENABLE ROW LEVEL SECURITY;

-- ==================== Service role bypass ====================
CREATE POLICY "Service role full access incident_events" ON incident_events FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access postmortems" ON postmortems FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access tags" ON tags FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access incident_tags" ON incident_tags FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access auto_tag_rules" ON auto_tag_rules FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access services" ON services FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access service_dependencies" ON service_dependencies FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access on_call_schedules" ON on_call_schedules FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access on_call_persons" ON on_call_persons FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access cost_entries" ON cost_entries FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access incident_comments" ON incident_comments FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access incident_watchers" ON incident_watchers FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access insights" ON insights FOR ALL USING (auth.role() = 'service_role');

-- ==================== Tenant isolation policies ====================
-- Helper: get current user's tenant_id
CREATE OR REPLACE FUNCTION get_user_tenant_id()
RETURNS UUID AS $$
    SELECT tenant_id FROM users WHERE id = auth.uid()
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- Tenant-scoped SELECT policies for each table
CREATE POLICY "Tenant isolation incident_events" ON incident_events FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation postmortems" ON postmortems FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation tags" ON tags FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation incident_tags" ON incident_tags FOR SELECT
    USING (incident_id IN (SELECT id FROM incidents WHERE tenant_id = get_user_tenant_id()));
CREATE POLICY "Tenant isolation auto_tag_rules" ON auto_tag_rules FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation services" ON services FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation service_dependencies" ON service_dependencies FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation on_call_schedules" ON on_call_schedules FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation on_call_persons" ON on_call_persons FOR SELECT
    USING (schedule_record_id IN (SELECT id FROM on_call_schedules WHERE tenant_id = get_user_tenant_id()));
CREATE POLICY "Tenant isolation cost_entries" ON cost_entries FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation incident_comments" ON incident_comments FOR SELECT USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant isolation incident_watchers" ON incident_watchers FOR SELECT
    USING (incident_id IN (SELECT id FROM incidents WHERE tenant_id = get_user_tenant_id()));
CREATE POLICY "Tenant isolation insights" ON insights FOR SELECT USING (tenant_id = get_user_tenant_id());

-- Tenant-scoped INSERT policies
CREATE POLICY "Tenant insert incident_events" ON incident_events FOR INSERT WITH CHECK (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant insert postmortems" ON postmortems FOR INSERT WITH CHECK (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant insert tags" ON tags FOR INSERT WITH CHECK (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant insert incident_comments" ON incident_comments FOR INSERT WITH CHECK (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant insert cost_entries" ON cost_entries FOR INSERT WITH CHECK (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant insert services" ON services FOR INSERT WITH CHECK (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant insert insights" ON insights FOR INSERT WITH CHECK (tenant_id = get_user_tenant_id());

-- Tenant-scoped UPDATE policies
CREATE POLICY "Tenant update postmortems" ON postmortems FOR UPDATE USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant update tags" ON tags FOR UPDATE USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant update incident_comments" ON incident_comments FOR UPDATE USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant update services" ON services FOR UPDATE USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant update insights" ON insights FOR UPDATE USING (tenant_id = get_user_tenant_id());

-- Tenant-scoped DELETE policies
CREATE POLICY "Tenant delete tags" ON tags FOR DELETE USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant delete incident_comments" ON incident_comments FOR DELETE USING (tenant_id = get_user_tenant_id());
CREATE POLICY "Tenant delete cost_entries" ON cost_entries FOR DELETE USING (tenant_id = get_user_tenant_id());

-- ==================== Triggers for updated_at ====================
CREATE TRIGGER update_postmortems_updated_at BEFORE UPDATE ON postmortems FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_tags_updated_at BEFORE UPDATE ON tags FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_services_updated_at BEFORE UPDATE ON services FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_on_call_schedules_updated_at BEFORE UPDATE ON on_call_schedules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_incident_comments_updated_at BEFORE UPDATE ON incident_comments FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_insights_updated_at BEFORE UPDATE ON insights FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_auto_tag_rules_updated_at BEFORE UPDATE ON auto_tag_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ==================== Comments ====================
COMMENT ON TABLE incident_events IS 'Timeline events for incidents';
COMMENT ON TABLE postmortems IS 'Postmortem documents linked to incidents';
COMMENT ON TABLE tags IS 'Tags for categorizing incidents';
COMMENT ON TABLE incident_tags IS 'Many-to-many: incidents <-> tags';
COMMENT ON TABLE services IS 'Service catalog';
COMMENT ON TABLE service_dependencies IS 'Service dependency graph';
COMMENT ON TABLE on_call_schedules IS 'On-call schedule configurations';
COMMENT ON TABLE on_call_persons IS 'Current on-call persons per schedule';
COMMENT ON TABLE cost_entries IS 'Cost tracking entries per incident';
COMMENT ON TABLE incident_comments IS 'Collaboration comments on incidents';
COMMENT ON TABLE incident_watchers IS 'Users watching an incident';
COMMENT ON TABLE insights IS 'AI-detected patterns and insights';
