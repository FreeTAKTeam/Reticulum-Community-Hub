import { createRouter } from "vue-router";
import { createWebHistory } from "vue-router";
import { MISSION_DOMAIN_ROUTE_NAMES } from "../types/missions/routes";
import { useConnectionStore } from "../stores/connection";

const DashboardPage = () => import("../pages/DashboardPage.vue");
const MissionsPage = () => import("../pages/MissionsPage.vue");
const MissionsLegacyPage = () => import("../pages/missions/MissionsLegacyPage.vue");
const MissionAssetsPage = () => import("../pages/MissionAssetsPage.vue");
const MissionLogsPage = () => import("../pages/MissionLogsPage.vue");
const ChecklistsPage = () => import("../pages/ChecklistsPage.vue");
const WebMapPage = () => import("../pages/WebMapPage.vue");
const TopicsPage = () => import("../pages/TopicsPage.vue");
const FilesPage = () => import("../pages/FilesPage.vue");
const ChatPage = () => import("../pages/ChatPage.vue");
const UsersPage = () => import("../pages/UsersPage.vue");
const TeamRosterPage = () => import("../pages/TeamRosterPage.vue");
const ConfigurePage = () => import("../pages/ConfigurePage.vue");
const AboutPage = () => import("../pages/AboutPage.vue");
const ConnectPage = () => import("../pages/ConnectPage.vue");

const MissionsWorkspacePage = () => import("../pages/missions/MissionsWorkspacePage.vue");
const MissionOverviewPage = () => import("../pages/missions/domains/MissionOverviewPage.vue");
const MissionObjectPage = () => import("../pages/missions/domains/MissionObjectPage.vue");
const TopicObjectPage = () => import("../pages/missions/domains/TopicObjectPage.vue");
const ChecklistObjectPage = () => import("../pages/missions/domains/ChecklistObjectPage.vue");
const ChecklistTaskObjectPage = () => import("../pages/missions/domains/ChecklistTaskObjectPage.vue");
const ChecklistTemplateObjectPage = () => import("../pages/missions/domains/ChecklistTemplateObjectPage.vue");
const TeamObjectPage = () => import("../pages/missions/domains/TeamObjectPage.vue");
const TeamMemberObjectPage = () => import("../pages/missions/domains/TeamMemberObjectPage.vue");
const SkillObjectPage = () => import("../pages/missions/domains/SkillObjectPage.vue");
const TeamMemberSkillObjectPage = () => import("../pages/missions/domains/TeamMemberSkillObjectPage.vue");
const TaskSkillRequirementObjectPage = () => import("../pages/missions/domains/TaskSkillRequirementObjectPage.vue");
const AssetObjectPage = () => import("../pages/missions/domains/AssetObjectPage.vue");
const AssignmentObjectPage = () => import("../pages/missions/domains/AssignmentObjectPage.vue");
const ZoneObjectPage = () => import("../pages/missions/domains/ZoneObjectPage.vue");
const DomainEventObjectPage = () => import("../pages/missions/domains/DomainEventObjectPage.vue");
const MissionChangeObjectPage = () => import("../pages/missions/domains/MissionChangeObjectPage.vue");
const LogEntryObjectPage = () => import("../pages/missions/domains/LogEntryObjectPage.vue");
const SnapshotObjectPage = () => import("../pages/missions/domains/SnapshotObjectPage.vue");
const AuditEventObjectPage = () => import("../pages/missions/domains/AuditEventObjectPage.vue");

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: DashboardPage },
    { path: "/missions", name: "missions", component: MissionsLegacyPage },
    { path: "/missions/legacy", name: "missions-legacy", component: MissionsLegacyPage },
    { path: "/missions/domain", name: "missions-domain-entry", component: MissionsPage },
    { path: "/missions/assets", name: "mission-assets", component: MissionAssetsPage },
    { path: "/missions/logs", name: "mission-logs", component: MissionLogsPage },
    {
      path: "/missions/:mission_uid",
      component: MissionsWorkspacePage,
      children: [
        {
          path: "",
          name: MISSION_DOMAIN_ROUTE_NAMES.root,
          redirect: (to) => ({
            name: MISSION_DOMAIN_ROUTE_NAMES.overview,
            params: to.params,
            query: {
              ...to.query,
              mission_uid: String(to.params.mission_uid ?? "")
            }
          })
        },
        { path: "overview", name: MISSION_DOMAIN_ROUTE_NAMES.overview, component: MissionOverviewPage },
        { path: "mission", name: MISSION_DOMAIN_ROUTE_NAMES.mission, component: MissionObjectPage },
        { path: "topic", name: MISSION_DOMAIN_ROUTE_NAMES.topic, component: TopicObjectPage },
        { path: "checklists", name: MISSION_DOMAIN_ROUTE_NAMES.checklist, component: ChecklistObjectPage },
        {
          path: "checklist-tasks",
          name: MISSION_DOMAIN_ROUTE_NAMES.checklistTask,
          component: ChecklistTaskObjectPage
        },
        {
          path: "checklist-templates",
          name: MISSION_DOMAIN_ROUTE_NAMES.checklistTemplate,
          component: ChecklistTemplateObjectPage
        },
        { path: "teams", name: MISSION_DOMAIN_ROUTE_NAMES.team, component: TeamObjectPage },
        { path: "team-members", name: MISSION_DOMAIN_ROUTE_NAMES.teamMember, component: TeamMemberObjectPage },
        { path: "skills", name: MISSION_DOMAIN_ROUTE_NAMES.skill, component: SkillObjectPage },
        {
          path: "team-member-skills",
          name: MISSION_DOMAIN_ROUTE_NAMES.teamMemberSkill,
          component: TeamMemberSkillObjectPage
        },
        {
          path: "task-skill-requirements",
          name: MISSION_DOMAIN_ROUTE_NAMES.taskSkillRequirement,
          component: TaskSkillRequirementObjectPage
        },
        { path: "assets", name: MISSION_DOMAIN_ROUTE_NAMES.asset, component: AssetObjectPage },
        { path: "assignments", name: MISSION_DOMAIN_ROUTE_NAMES.assignment, component: AssignmentObjectPage },
        { path: "zones", name: MISSION_DOMAIN_ROUTE_NAMES.zone, component: ZoneObjectPage },
        { path: "domain-events", name: MISSION_DOMAIN_ROUTE_NAMES.domainEvent, component: DomainEventObjectPage },
        {
          path: "mission-changes",
          name: MISSION_DOMAIN_ROUTE_NAMES.missionChange,
          component: MissionChangeObjectPage
        },
        { path: "log-entries", name: MISSION_DOMAIN_ROUTE_NAMES.logEntry, component: LogEntryObjectPage },
        { path: "snapshots", name: MISSION_DOMAIN_ROUTE_NAMES.snapshot, component: SnapshotObjectPage },
        { path: "audit-events", name: MISSION_DOMAIN_ROUTE_NAMES.auditEvent, component: AuditEventObjectPage }
      ]
    },
    { path: "/checklists", name: "checklists", component: ChecklistsPage },
    { path: "/webmap", name: "webmap", component: WebMapPage },
    { path: "/topics", name: "topics", component: TopicsPage },
    { path: "/files", name: "files", component: FilesPage },
    { path: "/chat", name: "chat", component: ChatPage },
    { path: "/users", name: "users", component: UsersPage },
    { path: "/users/teams/members", name: "team-roster", component: TeamRosterPage },
    { path: "/configure", name: "configure", component: ConfigurePage },
    { path: "/about", name: "about", component: AboutPage },
    { path: "/connect", name: "connect", component: ConnectPage }
  ]
});


const PUBLIC_ROUTES = new Set(["connect", "about"]);

router.beforeEach((to) => {
  const connectionStore = useConnectionStore();
  const isPublicRoute = PUBLIC_ROUTES.has(String(to.name ?? "")) || to.path.startsWith("/Help") || to.path.startsWith("/Examples");
  if (isPublicRoute) {
    return true;
  }
  if (connectionStore.isRemoteTarget && !connectionStore.isAuthenticated) {
    return {
      path: "/connect",
      query: { redirect: to.fullPath }
    };
  }
  return true;
});

export default router;
