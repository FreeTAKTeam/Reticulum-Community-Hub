import { createRouter } from "vue-router";
import { createWebHistory } from "vue-router";

const DashboardPage = () => import("../pages/DashboardPage.vue");
const MissionsPage = () => import("../pages/MissionsPage.vue");
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

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: DashboardPage },
    { path: "/missions", name: "missions", component: MissionsPage },
    { path: "/missions/assets", name: "mission-assets", component: MissionAssetsPage },
    { path: "/missions/logs", name: "mission-logs", component: MissionLogsPage },
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

export default router;
