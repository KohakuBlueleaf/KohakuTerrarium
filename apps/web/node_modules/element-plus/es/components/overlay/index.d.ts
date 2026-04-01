import { EpPropFinalized, EpPropMergeType } from "../../utils/vue/props/types.js";
import { ZIndexType } from "../../utils/typescript.js";
import "../../utils/index.js";
import { OverlayEmits, OverlayProps, OverlayPropsPublic, overlayEmits, overlayProps } from "./src/overlay.js";
import * as vue from "vue";

//#region ../../packages/components/overlay/index.d.ts
declare const ElOverlay: vue.DefineComponent<vue.ExtractPropTypes<{
  readonly mask: EpPropFinalized<BooleanConstructor, unknown, unknown, true, boolean>;
  readonly customMaskEvent: BooleanConstructor;
  readonly overlayClass: {
    readonly type: vue.PropType<EpPropMergeType<(new (...args: any[]) => string | string[] | Record<string, boolean>) | (() => string | string[] | Record<string, boolean>) | (((new (...args: any[]) => string | string[] | Record<string, boolean>) | (() => string | string[] | Record<string, boolean>)) | null)[], unknown, unknown>>;
    readonly required: false;
    readonly validator: ((val: unknown) => boolean) | undefined;
    __epPropKey: true;
  };
  readonly zIndex: {
    readonly type: vue.PropType<EpPropMergeType<(new (...args: any[]) => number | "auto" | "inherit" | "initial" | "revert" | "revert-layer" | "unset") | (() => ZIndexType) | (((new (...args: any[]) => number | "auto" | "inherit" | "initial" | "revert" | "revert-layer" | "unset") | (() => ZIndexType)) | null)[], unknown, unknown>>;
    readonly required: false;
    readonly validator: ((val: unknown) => boolean) | undefined;
    __epPropKey: true;
  };
}>, () => vue.VNode<vue.RendererNode, vue.RendererElement, {
  [key: string]: any;
}>, {}, {}, {}, vue.ComponentOptionsMixin, vue.ComponentOptionsMixin, {
  click: (evt: MouseEvent) => boolean;
}, string, vue.PublicProps, Readonly<vue.ExtractPropTypes<{
  readonly mask: EpPropFinalized<BooleanConstructor, unknown, unknown, true, boolean>;
  readonly customMaskEvent: BooleanConstructor;
  readonly overlayClass: {
    readonly type: vue.PropType<EpPropMergeType<(new (...args: any[]) => string | string[] | Record<string, boolean>) | (() => string | string[] | Record<string, boolean>) | (((new (...args: any[]) => string | string[] | Record<string, boolean>) | (() => string | string[] | Record<string, boolean>)) | null)[], unknown, unknown>>;
    readonly required: false;
    readonly validator: ((val: unknown) => boolean) | undefined;
    __epPropKey: true;
  };
  readonly zIndex: {
    readonly type: vue.PropType<EpPropMergeType<(new (...args: any[]) => number | "auto" | "inherit" | "initial" | "revert" | "revert-layer" | "unset") | (() => ZIndexType) | (((new (...args: any[]) => number | "auto" | "inherit" | "initial" | "revert" | "revert-layer" | "unset") | (() => ZIndexType)) | null)[], unknown, unknown>>;
    readonly required: false;
    readonly validator: ((val: unknown) => boolean) | undefined;
    __epPropKey: true;
  };
}>> & Readonly<{
  onClick?: ((evt: MouseEvent) => any) | undefined;
}>, {
  readonly mask: EpPropMergeType<BooleanConstructor, unknown, unknown>;
  readonly customMaskEvent: boolean;
}, {}, {}, {}, string, vue.ComponentProvideOptions, true, {}, any>;
//#endregion
export { ElOverlay, ElOverlay as default, OverlayEmits, OverlayProps, OverlayPropsPublic, overlayEmits, overlayProps };