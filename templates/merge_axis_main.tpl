<%
    var_lower = "merge_axis_{:04d}_lower".format(idx)
    var_upper = "merge_axis_{:04d}_upper".format(idx)
    function_name = "merge_axis_{:04d}".format(idx)
%>

${var_lower} = 0
${var_upper} = 0

def ${function_name}(vjoy):
    vjoy[${entry["vjoy"]["device_id"]}].axis(${entry["vjoy"]["axis_id"]}).value = (${var_lower} - ${var_upper}) / 2.0