import './composer-settings.css';

const drawings={
 model:<><rect x="4" y="5" width="16" height="14" rx="4"/><path d="M9 2v3m6-3v3M8 10h.01M16 10h.01M9 14h6"/></>,
 thinking:<><path d="M9 18h6m-5 3h4M8 14c-2-1.5-3-3-3-5a7 7 0 0 1 14 0c0 2-1 3.5-3 5l-1 2H9l-1-2Z"/></>,
 mode:<path d="M4 7h16M4 17h16M8 4v6m8 4v6"/>,
 permission:<><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
 gpu:<><rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3"/></>,
};

export function ComposerSettingIcon({name}:{name:keyof typeof drawings}){
 return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{drawings[name]}</svg>;
}

/** Current values remain visible on hover/focus and in the trigger's accessible description. */
export function ComposerSettingValue({value}:{value:string}){
 return <span className="composer-setting-value" aria-hidden="true">当前：{value}</span>;
}
