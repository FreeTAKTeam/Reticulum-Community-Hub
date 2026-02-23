import { createRouter } from "vue-router";
import { createWebHistory } from "vue-router";
import AboutPage from "../pages/AboutPage.vue";
import ConfigurePage from "../pages/ConfigurePage.vue";
import ConnectPage from "../pages/ConnectPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import FilesPage from "../pages/FilesPage.vue";
import ChatPage from "../pages/ChatPage.vue";
import ChecklistsPage from "../pages/ChecklistsPage.vue";
import MissionAssetsPage from "../pages/MissionAssetsPage.vue";
import MissionLogsPage from "../pages/MissionLogsPage.vue";
import MissionsPage from "../pages/MissionsPage.vue";
import TeamRosterPage from "../pages/TeamRosterPage.vue";
import TopicsPage from "../pages/TopicsPage.vue";
import UsersPage from "../pages/UsersPage.vue";
import WebMapPage from "../pages/WebMapPage.vue";

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
