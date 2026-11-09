<script setup lang="ts">
import type { StudentQuestion } from '../../api/contracts';
defineProps<{
  question: StudentQuestion;
  index: number;
  modelValue: string[];
  disabled: boolean;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>();
function toggle(current: string[], value: string, checked: boolean) {
  emit(
    'update:modelValue',
    checked
      ? [...new Set([...current, value])]
      : current.filter((x) => x !== value),
  );
}
</script>
<template>
  <fieldset class="question-card" :disabled="disabled">
    <legend>
      <span class="eyebrow"
        >第 {{ index + 1 }} 题 ·
        {{
          question.type === 'single_choice'
            ? '单选题'
            : '多选题（完全匹配计分）'
        }}</span
      ><span class="question-stem">{{ question.stem }}</span>
    </legend>
    <label
      v-for="option in question.options"
      :key="option.option_id"
      class="option"
      :class="{ selected: modelValue.includes(option.option_id) }"
    >
      <input
        :type="question.type === 'single_choice' ? 'radio' : 'checkbox'"
        :name="question.question_id"
        :value="option.option_id"
        :checked="modelValue.includes(option.option_id)"
        @change="
          question.type === 'single_choice'
            ? emit('update:modelValue', [option.option_id])
            : toggle(
                modelValue,
                option.option_id,
                ($event.target as HTMLInputElement).checked,
              )
        "
      />
      <span class="option-label">{{ option.label }}</span
      ><span>{{ option.text }}</span>
    </label>
  </fieldset>
</template>
