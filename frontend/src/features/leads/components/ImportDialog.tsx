import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { parseCsv, mapCsvRowToLead } from "@/utils/csv";
import { leadsService } from "@/services/resources";
import { toast } from "sonner";
export function ImportDialog({open,onOpenChange}: {open:boolean;onOpenChange:(open:boolean)=>void}) {
 const [rows,setRows]=useState<ReturnType<typeof mapCsvRowToLead>[]>([]),[busy,setBusy]=useState(false);const q=useQueryClient();
 return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogTitle>Import contacts from CSV</DialogTitle><DialogDescription>Import a file you have permission to use. Columns: first name, last name, company, job title, LinkedIn URL, email, location, time zone (an IANA name such as Europe/Paris).</DialogDescription><label className="field">CSV file<input type="file" accept=".csv,text/csv" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>2000000){toast.error("Choose a file smaller than 2 MB");return;}setRows(parseCsv(await file.text()).map(mapCsvRowToLead));}}/></label><p>{rows.length} contacts ready to import</p><Button disabled={!rows.length} loading={busy} onClick={async()=>{setBusy(true);try{const r=await leadsService.bulkImport(rows,[]);await q.invalidateQueries();toast.success(`${r.created} contacts imported`);setRows([]);onOpenChange(false);}catch(e){toast.error((e as Error).message);}finally{setBusy(false);}}}>Import contacts</Button></DialogContent></Dialog>;
}
