# Mission & Checklist UI - Implementation Plan

## Current Status Overview

### ChecklistsPage.vue
**Implemented:**
- ✅ List view with stats (Total, Completed, Templates, Pending)
- ✅ Tab navigation (Active, Templates, Import CSV)
- ✅ Checklist detail view with info cards
- ✅ Task list with toggle completion
- ✅ Create checklist modal (basic)
- ✅ Link checklist to mission
- ✅ CSV upload preview

**Not Implemented ("Coming Soon"):**
- ❌ Edit checklist (shows toast only)
- ❌ Delete checklist (toast only, no API call)
- ❌ Template creation/editing
- ❌ CSV import (preview only, no actual import)
- ❌ Add task to checklist
- ❌ Edit task
- ❌ Delete task
- ❌ Task cell editing

### MissionsPage.vue
**Implemented:**
- ✅ Mission list with stats
- ✅ Mission detail view with tabs
- ✅ Create/Edit/Delete mission
- ✅ Overview tab
- ✅ Excheck tab (linked checklists)
- ✅ Add checklist modal (link existing)
- ✅ Navigation to create new checklist

**Not Implemented:**
- ❌ Team Members (returns 0)
- ❌ Markers tab (shows all markers, not mission-specific)
- ❌ Logs tab (basic display, no filtering/pagination)
- ❌ Edit linked checklist inline
- ❌ Remove checklist from mission
- ❌ Marker creation

---

## Implementation Plan

### Phase 1: Critical Missing Features (High Priority)

#### 1.1 Checklist - Edit & Delete
**Files:** `ChecklistsPage.vue`
**Tasks:**
- [ ] Create Edit Checklist modal (rename, change description, change mode)
- [ ] Implement DELETE API call for checklist deletion
- [ ] Add confirmation dialog for delete
- [ ] Update checklist list after edit/delete

**API Endpoints:**
- `PATCH /checklists/{uid}` - Update checklist
- `DELETE /checklists/{uid}` - Delete checklist

#### 1.2 Checklist - Task Management
**Files:** `ChecklistsPage.vue`
**Tasks:**
- [ ] Implement "Add Task" modal with form
- [ ] Create Task Edit modal (update cells, due date, notes)
- [ ] Add task delete with confirmation
- [ ] Implement task cell inline editing
- [ ] Add task reordering (drag & drop or move up/down)

**API Endpoints:**
- `POST /checklists/{uid}/tasks` - Add task
- `PATCH /checklists/{uid}/tasks/{task_uid}` - Update task
- `DELETE /checklists/{uid}/tasks/{task_uid}` - Delete task

#### 1.3 Mission - Team Members
**Files:** `MissionsPage.vue`
**Tasks:**
- [ ] Implement `loadTeamMembers()` API call
- [ ] Create Team Members tab UI
- [ ] Add member assignment to tasks
- [ ] Display member capabilities

**API Endpoints:**
- `GET /api/r3akt/team-members` - Load members
- `GET /api/r3akt/teams` - Load teams

---

### Phase 2: Enhanced Functionality (Medium Priority)

#### 2.1 Checklist - Template Management
**Files:** `ChecklistsPage.vue`
**Tasks:**
- [ ] Create Template Editor modal
- [ ] Implement template column configuration
- [ ] Add template CRUD operations
- [ ] Clone template functionality

**API Endpoints:**
- `POST /checklists/templates` - Create template
- `PATCH /checklists/templates/{id}` - Update template
- `DELETE /checklists/templates/{id}` - Delete template

#### 2.2 Checklist - CSV Import
**Files:** `ChecklistsPage.vue`
**Tasks:**
- [ ] Complete CSV import functionality
- [ ] Add column mapping UI
- [ ] Handle errors gracefully
- [ ] Show import progress

**API Endpoints:**
- `POST /checklists/import/csv` - Import CSV

#### 2.3 Mission - Checklist Management
**Files:** `MissionsPage.vue`
**Tasks:**
- [ ] Add "Remove from Mission" button on linked checklists
- [ ] Implement inline checklist progress view
- [ ] Add quick task completion from mission view
- [ ] Show checklist status indicators

---

### Phase 3: Advanced Features (Lower Priority)

#### 3.1 Mission - Markers Integration
**Files:** `MissionsPage.vue`
**Tasks:**
- [ ] Filter markers by mission
- [ ] Add marker creation from mission
- [ ] Link markers to checklist tasks
- [ ] Show marker count on mission card

#### 3.2 Mission - Logs Enhancement
**Files:** `MissionsPage.vue`
**Tasks:**
- [ ] Implement log filtering by type
- [ ] Add log pagination
- [ ] Export logs functionality
- [ ] Real-time log updates via WebSocket

#### 3.3 Cross-Feature Integration
**Files:** `ChecklistsPage.vue`, `MissionsPage.vue`
**Tasks:**
- [ ] Navigate from checklist to mission detail
- [ ] Show mission context in checklist view
- [ ] Bulk operations (bulk delete, bulk link)
- [ ] Search across missions and checklists

---

## Detailed Implementation Notes

### Checklist Edit Modal
```typescript
interface EditChecklistForm {
  name: string;
  description: string;
  mode: 'ONLINE' | 'OFFLINE';
  checklist_status: string;
}
```

### Task Management
Each task has:
- Task number (auto-increment)
- Cells (dynamic columns based on template)
- Due date (absolute or relative)
- Status (PENDING, COMPLETE, LATE)
- Notes
- Completion info (who, when)

### CSV Import Format
Expected CSV structure:
```csv
Task,Description,Due Minutes,Notes
"Task 1","Description",30,"Note"
```

### Team Member Integration
Members should show:
- Callsign/name
- Role
- Assigned tasks count
- Capabilities/skills

---

## API Endpoint Reference

### Checklists
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/checklists` | List all checklists |
| POST | `/checklists` | Create online checklist |
| POST | `/checklists/offline` | Create offline checklist |
| GET | `/checklists/{uid}` | Get checklist detail |
| PATCH | `/checklists/{uid}` | Update checklist |
| DELETE | `/checklists/{uid}` | Delete checklist |
| POST | `/checklists/{uid}/tasks` | Add task |
| PATCH | `/checklists/{uid}/tasks/{task_uid}` | Update task |
| DELETE | `/checklists/{uid}/tasks/{task_uid}` | Delete task |

### Templates
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/checklists/templates` | List templates |
| POST | `/checklists/templates` | Create template |
| PATCH | `/checklists/templates/{id}` | Update template |
| DELETE | `/checklists/templates/{id}` | Delete template |

### Missions
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/r3akt/missions` | List missions |
| POST | `/api/r3akt/missions` | Create mission |
| GET | `/api/r3akt/missions/{uid}` | Get mission detail |
| PATCH | `/api/r3akt/missions/{uid}` | Update mission |
| DELETE | `/api/r3akt/missions/{uid}` | Delete mission |
| GET | `/api/r3akt/teams` | List teams |
| GET | `/api/r3akt/team-members` | List team members |

---

## UI/UX Considerations

1. **Loading States**: Add skeleton loaders for all async operations
2. **Error Handling**: Show proper error messages for all API failures
3. **Confirmations**: Use confirmation dialogs for destructive actions
4. **Toast Notifications**: Provide feedback for all user actions
5. **Empty States**: Design helpful empty states for all views
6. **Responsive Design**: Ensure mobile-friendly layouts

## Testing Checklist

- [ ] Create/Edit/Delete checklist works end-to-end
- [ ] Task CRUD operations work
- [ ] CSV import handles various formats
- [ ] Mission linking/unlinking works
- [ ] Team members display correctly
- [ ] All toasts/errors show appropriately
- [ ] Navigation between views is smooth
