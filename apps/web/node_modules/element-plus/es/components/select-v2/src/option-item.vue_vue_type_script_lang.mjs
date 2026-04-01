import { useNamespace } from "../../../hooks/use-namespace/index.mjs";
import { useProps } from "./useProps.mjs";
import { useOption } from "./useOption.mjs";
import { optionV2Emits, optionV2Props } from "./defaults.mjs";
import { selectV2InjectionKey } from "./token.mjs";
import { defineComponent, inject } from "vue";

//#region ../../packages/components/select-v2/src/option-item.vue?vue&type=script&lang.ts
var option_item_vue_vue_type_script_lang_default = defineComponent({
	props: optionV2Props,
	emits: optionV2Emits,
	setup(props, { emit }) {
		const select = inject(selectV2InjectionKey);
		const ns = useNamespace("select");
		const { hoverItem, selectOptionClick } = useOption(props, { emit });
		const { getLabel } = useProps(select.props);
		return {
			ns,
			contentId: select.contentId,
			hoverItem,
			selectOptionClick,
			getLabel
		};
	}
});

//#endregion
export { option_item_vue_vue_type_script_lang_default as default };
//# sourceMappingURL=option-item.vue_vue_type_script_lang.mjs.map