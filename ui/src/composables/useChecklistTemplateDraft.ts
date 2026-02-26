type ChecklistTemplateColumnType = "SHORT_STRING" | "LONG_STRING" | "INTEGER" | "ACTUAL_TIME" | "RELATIVE_TIME";

type ChecklistTemplateColumnLike = {
  column_uid?: string | null;
  column_name?: string | null;
  display_order?: number | null;
  column_type?: string | null;
  column_editable?: boolean | null;
  is_removable?: boolean | null;
  system_key?: string | null;
  background_color?: string | null;
  text_color?: string | null;
};

type ChecklistTemplateDraftColumn = {
  column_uid: string;
  column_name: string;
  display_order: number;
  column_type: ChecklistTemplateColumnType;
  column_editable: boolean;
  is_removable: boolean;
  system_key: string | null;
  background_color: string | null;
  text_color: string | null;
};

type ChecklistTemplateColumnPayload = {
  column_uid: string;
  column_name: string;
  display_order: number;
  column_type: ChecklistTemplateColumnType;
  column_editable: boolean;
  is_removable: boolean;
  system_key?: string;
  background_color?: string;
  text_color?: string;
};

interface UseChecklistTemplateDraftOptions {
  buildTimestampTag: () => string;
  getDraftColumns: () => ChecklistTemplateDraftColumn[];
  setDraftColumns: (columns: ChecklistTemplateDraftColumn[]) => void;
  isReadonly: () => boolean;
  isSaving: () => boolean;
}

const SYSTEM_DUE_COLUMN_KEY = "DUE_RELATIVE_DTG";

const checklistTemplateColumnTypeOptions: ChecklistTemplateColumnType[] = [
  "SHORT_STRING",
  "LONG_STRING",
  "INTEGER",
  "ACTUAL_TIME",
  "RELATIVE_TIME"
];

const checklistTemplateColumnTypeSet = new Set<ChecklistTemplateColumnType>(checklistTemplateColumnTypeOptions);

export const useChecklistTemplateDraft = (options: UseChecklistTemplateDraftOptions) => {
  const normalizeChecklistTemplateColumnType = (value?: string | null): ChecklistTemplateColumnType => {
    const normalized = String(value ?? "").trim().toUpperCase() as ChecklistTemplateColumnType;
    if (checklistTemplateColumnTypeSet.has(normalized)) {
      return normalized;
    }
    return "SHORT_STRING";
  };

  const isChecklistTemplateDueColumn = (column?: { system_key?: string | null }): boolean =>
    String(column?.system_key ?? "")
      .trim()
      .toUpperCase() === SYSTEM_DUE_COLUMN_KEY;

  const buildChecklistTemplateColumnUid = (): string =>
    `tmpl-col-${options.buildTimestampTag().slice(-10)}-${Math.floor(Math.random() * 1_000_000)
      .toString(16)
      .padStart(5, "0")}`;

  const createDueChecklistTemplateDraftColumn = (): ChecklistTemplateDraftColumn => ({
    column_uid: buildChecklistTemplateColumnUid(),
    column_name: "Due",
    display_order: 1,
    column_type: "RELATIVE_TIME",
    column_editable: false,
    is_removable: false,
    system_key: SYSTEM_DUE_COLUMN_KEY,
    background_color: null,
    text_color: null
  });

  const createTaskChecklistTemplateDraftColumn = (): ChecklistTemplateDraftColumn => ({
    column_uid: buildChecklistTemplateColumnUid(),
    column_name: "Task",
    display_order: 2,
    column_type: "SHORT_STRING",
    column_editable: true,
    is_removable: true,
    system_key: null,
    background_color: null,
    text_color: null
  });

  const normalizeChecklistTemplateColor = (value?: string | null): string | null => {
    const normalized = String(value ?? "").trim();
    if (!normalized) {
      return null;
    }
    if (/^#[0-9a-fA-F]{6}$/.test(normalized)) {
      return normalized.toUpperCase();
    }
    return null;
  };

  const checklistTemplateColumnColorValue = (value?: string | null): string =>
    normalizeChecklistTemplateColor(value) ?? "#001F2B";

  const normalizeChecklistTemplateDraftColumns = (
    columns: ChecklistTemplateColumnLike[],
    opts?: { ensureTaskColumn?: boolean }
  ): ChecklistTemplateDraftColumn[] => {
    const normalizedRows = columns.map((column, index) => ({
      column_uid: String(column.column_uid ?? "").trim() || buildChecklistTemplateColumnUid(),
      column_name: String(column.column_name ?? `Column ${index + 1}`).trim() || `Column ${index + 1}`,
      display_order: Number(column.display_order ?? index + 1),
      column_type: normalizeChecklistTemplateColumnType(column.column_type),
      column_editable: Boolean(column.column_editable ?? true),
      is_removable: Boolean(column.is_removable ?? true),
      system_key: String(column.system_key ?? "").trim() || null,
      background_color: normalizeChecklistTemplateColor(column.background_color),
      text_color: normalizeChecklistTemplateColor(column.text_color)
    }));

    const sorted = [...normalizedRows].sort((left, right) => left.display_order - right.display_order);
    const dueColumn = sorted.find((column) => isChecklistTemplateDueColumn(column)) ?? createDueChecklistTemplateDraftColumn();
    const normalizedDueColumn: ChecklistTemplateDraftColumn = {
      ...dueColumn,
      column_name: String(dueColumn.column_name || "Due"),
      column_type: "RELATIVE_TIME",
      column_editable: false,
      is_removable: false,
      system_key: SYSTEM_DUE_COLUMN_KEY
    };

    const customColumns: ChecklistTemplateDraftColumn[] = sorted
      .filter((column) => !isChecklistTemplateDueColumn(column))
      .map((column) => ({
        ...column,
        system_key: null,
        column_type: normalizeChecklistTemplateColumnType(column.column_type)
      }));

    if (opts?.ensureTaskColumn && !customColumns.length) {
      customColumns.push(createTaskChecklistTemplateDraftColumn());
    }

    return [normalizedDueColumn, ...customColumns].map((column, index) => ({
      ...column,
      display_order: index + 1
    }));
  };

  const toChecklistTemplateColumnPayload = (columns: ChecklistTemplateDraftColumn[]): ChecklistTemplateColumnPayload[] =>
    normalizeChecklistTemplateDraftColumns(columns).map((column, index) => ({
      column_uid: column.column_uid || buildChecklistTemplateColumnUid(),
      column_name: String(column.column_name ?? "").trim() || `Column ${index + 1}`,
      display_order: index + 1,
      column_type: normalizeChecklistTemplateColumnType(column.column_type),
      column_editable: isChecklistTemplateDueColumn(column) ? false : Boolean(column.column_editable),
      is_removable: isChecklistTemplateDueColumn(column) ? false : Boolean(column.is_removable),
      system_key: isChecklistTemplateDueColumn(column) ? SYSTEM_DUE_COLUMN_KEY : undefined,
      background_color: normalizeChecklistTemplateColor(column.background_color) ?? undefined,
      text_color: normalizeChecklistTemplateColor(column.text_color) ?? undefined
    }));

  const validateChecklistTemplateDraftPayload = (
    templateName: string,
    columns: ChecklistTemplateDraftColumn[]
  ): string | null => {
    if (!templateName.trim()) {
      return "Template name is required";
    }
    const normalizedColumns = normalizeChecklistTemplateDraftColumns(columns);
    if (!normalizedColumns.length) {
      return "Template must include at least one column";
    }
    if (!isChecklistTemplateDueColumn(normalizedColumns[0])) {
      return "Due Relative DTG system column must be first";
    }
    const dueColumns = normalizedColumns.filter((column) => isChecklistTemplateDueColumn(column));
    if (dueColumns.length !== 1) {
      return "Exactly one Due Relative DTG system column is required";
    }
    if (dueColumns[0].column_type !== "RELATIVE_TIME") {
      return "Due Relative DTG system column must be RELATIVE_TIME";
    }
    if (dueColumns[0].is_removable) {
      return "Due Relative DTG system column cannot be removable";
    }
    const invalidType = normalizedColumns.find((column) => !checklistTemplateColumnTypeSet.has(column.column_type));
    if (invalidType) {
      return `Unsupported column type: ${invalidType.column_type}`;
    }
    return null;
  };

  const createBlankChecklistTemplateDraftColumns = (): ChecklistTemplateDraftColumn[] =>
    normalizeChecklistTemplateDraftColumns([createDueChecklistTemplateDraftColumn(), createTaskChecklistTemplateDraftColumn()], {
      ensureTaskColumn: true
    });

  const mutateChecklistTemplateDraftColumns = (
    mutate: (columns: ChecklistTemplateDraftColumn[]) => ChecklistTemplateDraftColumn[]
  ): void => {
    if (options.isReadonly() || options.isSaving()) {
      return;
    }
    const cloned = options.getDraftColumns().map((column) => ({ ...column }));
    const mutated = mutate(cloned);
    options.setDraftColumns(normalizeChecklistTemplateDraftColumns(mutated, { ensureTaskColumn: true }));
  };

  const setChecklistTemplateColumnName = (columnIndex: number, event: Event): void => {
    const value = String((event.target as HTMLInputElement | null)?.value ?? "");
    mutateChecklistTemplateDraftColumns((columns) =>
      columns.map((column, index) =>
        index === columnIndex && !isChecklistTemplateDueColumn(column)
          ? { ...column, column_name: value.trim() || column.column_name }
          : column
      )
    );
  };

  const setChecklistTemplateColumnType = (columnIndex: number, event: Event): void => {
    const value = String((event.target as HTMLSelectElement | null)?.value ?? "");
    mutateChecklistTemplateDraftColumns((columns) =>
      columns.map((column, index) =>
        index === columnIndex && !isChecklistTemplateDueColumn(column)
          ? { ...column, column_type: normalizeChecklistTemplateColumnType(value) }
          : column
      )
    );
  };

  const setChecklistTemplateColumnEditable = (columnIndex: number, event: Event): void => {
    const checked = Boolean((event.target as HTMLInputElement | null)?.checked);
    mutateChecklistTemplateDraftColumns((columns) =>
      columns.map((column, index) =>
        index === columnIndex && !isChecklistTemplateDueColumn(column)
          ? { ...column, column_editable: checked }
          : column
      )
    );
  };

  const setChecklistTemplateColumnBackgroundColor = (columnIndex: number, event: Event): void => {
    const value = String((event.target as HTMLInputElement | null)?.value ?? "");
    mutateChecklistTemplateDraftColumns((columns) =>
      columns.map((column, index) =>
        index === columnIndex ? { ...column, background_color: normalizeChecklistTemplateColor(value) } : column
      )
    );
  };

  const setChecklistTemplateColumnTextColor = (columnIndex: number, event: Event): void => {
    const value = String((event.target as HTMLInputElement | null)?.value ?? "");
    mutateChecklistTemplateDraftColumns((columns) =>
      columns.map((column, index) =>
        index === columnIndex ? { ...column, text_color: normalizeChecklistTemplateColor(value) } : column
      )
    );
  };

  const addChecklistTemplateColumn = (): void => {
    mutateChecklistTemplateDraftColumns((columns) => {
      const customCount = columns.filter((column) => !isChecklistTemplateDueColumn(column)).length;
      return [
        ...columns,
        {
          column_uid: buildChecklistTemplateColumnUid(),
          column_name: `Field ${customCount + 1}`,
          display_order: columns.length + 1,
          column_type: "SHORT_STRING",
          column_editable: true,
          is_removable: true,
          system_key: null,
          background_color: null,
          text_color: null
        }
      ];
    });
  };

  const canMoveChecklistTemplateColumnUp = (columnIndex: number): boolean => {
    if (options.isReadonly() || options.isSaving()) {
      return false;
    }
    const column = options.getDraftColumns()[columnIndex];
    if (!column || isChecklistTemplateDueColumn(column)) {
      return false;
    }
    if (columnIndex <= 1) {
      return false;
    }
    return true;
  };

  const canMoveChecklistTemplateColumnDown = (columnIndex: number): boolean => {
    if (options.isReadonly() || options.isSaving()) {
      return false;
    }
    const columns = options.getDraftColumns();
    const column = columns[columnIndex];
    if (!column || isChecklistTemplateDueColumn(column)) {
      return false;
    }
    return columnIndex >= 1 && columnIndex < columns.length - 1;
  };

  const moveChecklistTemplateColumnUp = (columnIndex: number): void => {
    if (!canMoveChecklistTemplateColumnUp(columnIndex)) {
      return;
    }
    mutateChecklistTemplateDraftColumns((columns) => {
      const next = [...columns];
      const previousIndex = columnIndex - 1;
      [next[previousIndex], next[columnIndex]] = [next[columnIndex], next[previousIndex]];
      return next;
    });
  };

  const moveChecklistTemplateColumnDown = (columnIndex: number): void => {
    if (!canMoveChecklistTemplateColumnDown(columnIndex)) {
      return;
    }
    mutateChecklistTemplateDraftColumns((columns) => {
      const next = [...columns];
      const nextIndex = columnIndex + 1;
      [next[nextIndex], next[columnIndex]] = [next[columnIndex], next[nextIndex]];
      return next;
    });
  };

  const canDeleteChecklistTemplateColumn = (columnIndex: number): boolean => {
    if (options.isReadonly() || options.isSaving()) {
      return false;
    }
    const column = options.getDraftColumns()[columnIndex];
    if (!column || isChecklistTemplateDueColumn(column)) {
      return false;
    }
    return Boolean(column.is_removable);
  };

  const deleteChecklistTemplateColumn = (columnIndex: number): void => {
    if (!canDeleteChecklistTemplateColumn(columnIndex)) {
      return;
    }
    mutateChecklistTemplateDraftColumns((columns) => columns.filter((_, index) => index !== columnIndex));
  };

  return {
    checklistTemplateColumnTypeOptions,
    checklistTemplateColumnColorValue,
    isChecklistTemplateDueColumn,
    normalizeChecklistTemplateDraftColumns,
    toChecklistTemplateColumnPayload,
    validateChecklistTemplateDraftPayload,
    createBlankChecklistTemplateDraftColumns,
    setChecklistTemplateColumnName,
    setChecklistTemplateColumnType,
    setChecklistTemplateColumnEditable,
    setChecklistTemplateColumnBackgroundColor,
    setChecklistTemplateColumnTextColor,
    addChecklistTemplateColumn,
    canMoveChecklistTemplateColumnUp,
    canMoveChecklistTemplateColumnDown,
    moveChecklistTemplateColumnUp,
    moveChecklistTemplateColumnDown,
    canDeleteChecklistTemplateColumn,
    deleteChecklistTemplateColumn
  };
};
