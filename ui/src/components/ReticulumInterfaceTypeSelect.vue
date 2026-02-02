<template>
  <div class="cui-combobox">
    <label v-if="label" class="cui-combobox__label">{{ label }}</label>
    <div class="cui-combobox__control">
      <select :value="modelValue" class="cui-combobox__select" @change="onChange">
        <option value="" disabled>Pick a category...</option>
        <optgroup v-for="group in groups" :key="group.label" :label="group.label">
          <option v-for="option in group.options" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </optgroup>
      </select>
      <span class="cui-combobox__chevron" aria-hidden="true"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
type OptionGroup = {
  label: string;
  options: { label: string; value: string }[];
};

const props = withDefaults(
  defineProps<{
    modelValue: string;
    label?: string;
  }>(),
  {
    label: "Type"
  }
);

const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();

const groups: OptionGroup[] = [
  {
    label: "Automatic",
    options: [{ label: "Auto Interface", value: "AutoInterface" }]
  },
  {
    label: "RNodes",
    options: [
      { label: "RNode Interface", value: "RNodeInterface" },
      { label: "RNode IP Interface", value: "RNodeIPInterface" },
      { label: "RNode Multi Interface", value: "RNodeMultiInterface" }
    ]
  },
  {
    label: "IP Networks",
    options: [
      { label: "TCP Client Interface", value: "TCPClientInterface" },
      { label: "TCP Server Interface", value: "TCPServerInterface" },
      { label: "UDP Interface", value: "UDPInterface" },
      { label: "I2P Interface", value: "I2PInterface" }
    ]
  },
  {
    label: "Hardware",
    options: [
      { label: "Serial Interface", value: "SerialInterface" },
      { label: "KISS Interface", value: "KISSInterface" },
      { label: "AX.25 KISS Interface", value: "AX25KISSInterface" }
    ]
  },
  {
    label: "Pipelines",
    options: [{ label: "Pipe Interface", value: "PipeInterface" }]
  }
];

const onChange = (event: Event) => {
  const target = event.target as HTMLSelectElement;
  emit("update:modelValue", target.value);
};
</script>
