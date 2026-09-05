// Report references and containing functions for one or more addresses.
//@category PS5

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class FindAddressReferences extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length == 0) {
            printerr("usage: FindAddressReferences <address> [...]");
            return;
        }
        for (String value : args) {
            Address target = toAddr(value);
            println("TARGET " + target);
            ReferenceIterator refs = currentProgram.getReferenceManager()
                .getReferencesTo(target);
            int count = 0;
            while (refs.hasNext()) {
                Reference ref = refs.next();
                Address from = ref.getFromAddress();
                Function function = getFunctionContaining(from);
                println("REF " + from + " " + ref.getReferenceType() +
                    " FUNCTION " + (function == null ? "none" :
                    function.getName() + "@" + function.getEntryPoint()));
                count++;
            }
            println("COUNT " + count);
        }
    }
}
