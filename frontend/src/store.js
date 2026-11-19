import{api}from'./api.js';
export const state={user:null,data:null};
export async function refresh(){let[archive,recommendations]=await Promise.all([api('/archive'),api('/receipts/recommendations')]);state.data=Object.assign(archive,{recommendations});return state}
