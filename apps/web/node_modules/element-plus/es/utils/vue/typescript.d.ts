import { AppContext, EmitsOptions, ObjectPlugin, SetupContext } from "vue";

//#region ../../packages/utils/vue/typescript.d.ts
type SFCWithInstall<T> = T & ObjectPlugin & SFCWithPropsDefaultsSetter<T>;
type SFCInstallWithContext<T> = SFCWithInstall<T> & {
  _context: AppContext | null;
};
type SFCWithPropsDefaultsSetter<T> = T extends (new (...args: any) => any) ? {
  setPropsDefaults: (defaults: Partial<InstanceType<T>['$props']>) => void;
} : unknown;
type EmitFn<E extends EmitsOptions> = SetupContext<E>['emit'];
//#endregion
export { EmitFn, SFCInstallWithContext, SFCWithInstall, SFCWithPropsDefaultsSetter };