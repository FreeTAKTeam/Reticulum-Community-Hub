# ChecklistsPage Test Plan

## CSV Import from Templates Tab

### Test 1: CSV Import UI Navigation
**Steps:**
1. Navigate to `/checklists`
2. Click on "Templates" tab
3. Click "Import from CSV" button at bottom of template list

**Expected:**
- CSV Import UI appears (two-column layout: Upload on left, Preview on right)
- "Back" button visible
- "Choose File" button visible
- No errors in console

---

### Test 2: CSV File Upload
**Steps:**
1. In CSV Import UI, click "Choose File"
2. Select a valid CSV file with headers (e.g., `Task,Due,Assignee`)
3. Click Open

**Expected:**
- Filename appears next to button
- "Header Columns" count shows correct number
- "Task Rows" count shows correct number (rows excluding header)
- Preview table appears on right showing data
- No errors in console

**Test Files:**
```csv
Task,Due,Assignee
Setup equipment,30,John
Test comms,45,Jane
Deploy unit,60,Team A
```

---

### Test 3: CSV Import Creates Template
**Steps:**
1. Upload CSV file
2. Click "Import" button
3. Wait for completion

**Expected:**
- Template is created successfully
- User is redirected back to Templates list
- New template appears in list with name matching CSV filename
- Template shows "CSV Import" chip
- Success toast message appears
- Template can be selected and edited

---

### Test 4: CSV Import Cancel/Back
**Steps:**
1. Click "Import from CSV"
2. Click "Back" button without importing

**Expected:**
- Returns to Templates list
- No template created
- File selection cleared

---

### Test 5: CSV Import with Due Column
**Steps:**
1. Import CSV with "Due" or "Due Relative Minutes" column
2. Select the imported template

**Expected:**
- Template has "Due" column as first column
- Column type is "RELATIVE_TIME"
- Column is not editable and not removable

**Test File:**
```csv
Due,Task,Notes
30,Setup equipment,High priority
45,Test comms,Check radio
```

---

## Template Builder

### Test 6: Create New Template
**Steps:**
1. In Templates tab, click "New" button
2. Enter template name
3. Add columns using "Add Column"
4. Click "Save"

**Expected:**
- Template saved successfully
- Appears in template list
- Success toast shown

---

### Test 7: Edit Existing Template
**Steps:**
1. Select existing template from list
2. Change template name or description
3. Click "Save"

**Expected:**
- Save button enables when changes made
- Template updated successfully
- Success toast shown

---

### Test 8: Save As New (Clone with new name)
**Steps:**
1. Select existing template
2. Change the name
3. Click "Save As New"

**Expected:**
- New template created with new name
- Original template unchanged
- New template appears in list
- Success toast shown

---

### Test 9: Clone Template
**Steps:**
1. Select existing template
2. Click "Clone" button

**Expected:**
- New template created with "Copy" suffix
- All columns copied
- Success toast shown

---

### Test 10: Archive Template
**Steps:**
1. Select existing template
2. Click "Archive" button

**Expected:**
- Template name gets "[ARCHIVED]" suffix
- Template saved
- Success toast shown

---

### Test 11: Delete Template
**Steps:**
1. Select existing template
2. Click "Delete" button
3. Confirm deletion

**Expected:**
- Template removed from list
- Success toast shown
- Editor shows blank/new template

---

### Test 12: Column Management
**Steps:**
1. Create new template or edit existing
2. Click "Add Column" - verify column added
3. Change column name - verify editable
4. Change column type - verify dropdown works
5. Toggle "Editable" checkbox - verify toggles
6. Click "Up"/"Down" arrows - verify reordering
7. Click "Delete" on a column - verify removal

**Expected:**
- All column operations work
- Due column (first) cannot be moved or deleted
- Changes enable Save button

---

## Checklist Creation from Templates

### Test 13: Create Checklist from Template
**Steps:**
1. Click "New" button in Active tab
2. Select a template
3. Enter checklist name
4. Click "Create"

**Expected:**
- Checklist created
- Redirected to checklist detail view
- Tasks populated from template

---

## Edge Cases

### Test 14: Empty CSV Import
**Steps:**
1. Try to import empty CSV or CSV with only header

**Expected:**
- Error message shown
- Import button disabled

---

### Test 15: Invalid CSV File Type
**Steps:**
1. Try to upload .txt or .json file

**Expected:**
- Error message: "Select a file with .csv extension"
- Import fails gracefully

---

### Test 16: Concurrent Operations
**Steps:**
1. Click Import while another import is loading

**Expected:**
- Button shows loading state
- Cannot trigger duplicate requests

---

## Regression Tests

### Test 17: Active Checklists Tab
**Steps:**
1. Verify "Import from CSV" button NOT in Active tab
2. Verify checklist list displays correctly
3. Verify checklist detail view works
4. Verify task completion toggles work

---

### Test 18: Navigation Between Tabs
**Steps:**
1. Switch between Active and Templates tabs
2. Verify state preserved correctly
3. Verify no console errors

---

## Pre-existing Issues (Not Blockers)

The following TypeScript warnings exist but do not affect functionality:
- Type predicate warnings in `collectChecklistTemplateOptions`
- Column type compatibility warnings

These should be fixed in a separate refactoring task.
