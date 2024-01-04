import adsk.core
import adsk.fusion
import math
import os
import collections

from typing import List
from ...lib import fusion360utils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

UP = adsk.core.Vector3D.create(0.0, 1.0, 0.0)
DOWN = adsk.core.Vector3D.create(0.0, -1.0, 0.0)
RIGHT = adsk.core.Vector3D.create(1.0, 0.0, 0.0)
LEFT = adsk.core.Vector3D.create(-1.0, 0.0, 0.0)
FORWARD = adsk.core.Vector3D.create(0.0, 0.0, 1.0)
BACKWARD = adsk.core.Vector3D.create(0.0, 0.0, -1.0)
ZERO = adsk.core.Point3D.create()

SIZE_CONF = {
    'M5': {
        'bore_diameter': '5mm',
        'socket_diameter': '8.5mm',
        'socket_length': '5mm',
        'hex_nut_diameter': '8mm',
        'hex_nut_length': '4mm'
    },
    'M4': {
        'bore_diameter': '4mm',
        'socket_diameter': '7mm',
        'socket_length': '4mm',
        'hex_nut_diameter': '7mm',
        'hex_nut_length': '3.2mm'
    },
    'M3': {
        'bore_diameter': '3mm',
        'socket_diameter': '5.5mm',
        'socket_length': '3mm',
        'hex_nut_diameter': '5.5mm',
        'hex_nut_length': '2.4mm'
    },
    'M2.5': {
        'bore_diameter': '2.5mm',
        'socket_diameter': '4.4mm',
        'socket_length': '2.2mm',
        'hex_nut_diameter': '4.8mm',
        'hex_nut_length': '2.0mm'
    },
    'M2': {
        'bore_diameter': '2mm',
        'socket_diameter': '3.8mm',
        'socket_length': '2.0mm',
        'hex_nut_diameter': '4mm',
        'hex_nut_length': '1.6mm'
    }
}
SIZE_DEFAULT = 'M3'

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cutFastenerHoleDialog'
CMD_NAME = 'Cut Fastener Hole'
CMD_DESC = 'Cutout a fastener profile around a given point'
IS_PROMOTED = False
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidModifyPanel'
COMMAND_BESIDE_ID = 'FusionPartingLineSplitCmd'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')
local_handlers = []


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESC, ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Get the panel the button will be created in.
    panel = workspace.toolbarPanels.itemById(PANEL_ID)

    # Create the button command control in the UI after the specified existing command.
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

    # Specify if the command is promoted to the main toolbar. 
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    inputs = args.command.commandInputs
    point_input = inputs.addSelectionInput('fastener_point', 'Head Point', 'Sketch Point to center the cut head on')
    point_input.setSelectionLimits(1, 1)
    point_input.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
    face_input = inputs.addSelectionInput('fastener_limit', 'Anchor Face', 'Face to terminate the cut anchor on')
    face_input.setSelectionLimits(1, 1)
    face_input.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
    size_input = inputs.addDropDownCommandInput('fastener_size', 'Size', adsk.core.DropDownStyles.TextListDropDownStyle)
    for key in SIZE_CONF:
        size_input.listItems.add(key, key == SIZE_DEFAULT)

    head_input = inputs.addDropDownCommandInput('fastener_head', 'Head Type', adsk.core.DropDownStyles.TextListDropDownStyle)
    head_input.listItems.add('Socket', True)
    head_input.listItems.add('None', False)
    anchor_input = inputs.addDropDownCommandInput('fastener_anchor', 'Anchor Type', adsk.core.DropDownStyles.TextListDropDownStyle)
    anchor_input.listItems.add('Hex Nut', True)
    anchor_input.listItems.add('None', False)
    inputs.addBoolValueInput('fastener_invert', 'Invert', True, "", False)
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event START')
    start_timeline_position = get_timeline_position()
    inputs = args.command.commandInputs
    limit_face = get_limit_input_value(inputs)
    facet_comp = make_facet_comp(inputs)
    sketch_timeline_position = get_timeline_position()
    cut_bore(inputs, facet_comp, limit_face, sketch_timeline_position)
    cut_head(inputs, facet_comp, limit_face, sketch_timeline_position)
    cut_anchor(inputs, facet_comp, limit_face, sketch_timeline_position)
    make_timeline_group(start_timeline_position, 'cut-fastener-hole')


def make_sketch(comp: adsk.fusion.Component, ref_point: adsk.fusion.SketchPoint, name: str, timeline_position: int):
    current_position = get_timeline_position()
    roll_timeline_to(timeline_position)
    new_sketch = comp.sketches.add(ref_point.parentSketch.referencePlane)
    new_sketch.name = name
    roll_timeline_to(current_position+1)
    return new_sketch


def roll_timeline_to(position: int):
    app = adsk.core.Application.get()
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    design.timeline.markerPosition = position

def get_timeline_position():
    app = adsk.core.Application.get()
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    return design.timeline.markerPosition

def make_timeline_group(start: int, name: str):
    app = adsk.core.Application.get()
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    timeline_group = design.timeline.timelineGroups.add(start, get_timeline_position() - 1)
    timeline_group.name = name
    return timeline_group


def find_exact_outer_profile(sketch: adsk.fusion.Sketch, curves: List[adsk.fusion.SketchEntity]):
    curve_tokens = []
    for curve in curves:
        curve_tokens.append(curve.entityToken)
    curve_counter =  collections.Counter(curve_tokens)
    for profile in sketch.profiles:
        loops = profile.profileLoops
        for loop in loops:
            if not loop.isOuter:
                continue

            loop_tokens = []
            for curve in loop.profileCurves:
                loop_tokens.append(curve.sketchEntity.entityToken)
            if not collections.Counter(loop_tokens) == curve_counter:
                continue
           
            return profile
    raise BaseException(f"unable to locate exact outer profile in {sketch.name}")


def make_facet_comp(inputs: adsk.core.CommandInputs):
    facet_point = get_point_input_value(inputs)
    facet_sketch = facet_point.parentSketch
    facet_comp = facet_sketch.parentComponent.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
    facet_comp.name = 'facet'
    return facet_comp


def get_limit_input_value(inputs: adsk.core.CommandInputs):
    limit_input: adsk.core.SelectionCommandInput = inputs.itemById('fastener_limit')
    limit_face:  adsk.fusion.BRepFace = limit_input.selection(0).entity
    return limit_face


def get_point_input_value(inputs: adsk.core.CommandInputs):
     point_input: adsk.core.SelectionCommandInput = inputs.itemById('fastener_point')
     facet_point: adsk.fusion.SketchPoint = point_input.selection(0).entity
     return facet_point


def get_inverted_input_value(inputs: adsk.core.CommandInputs):
    invert_input: adsk.core.BoolValueCommandInput = inputs.itemById('fastener_invert')
    return invert_input.value


def get_size_prop(inputs: adsk.core.CommandInputs, name: str):
    unitsManager = app.activeProduct.unitsManager
    size_input: adsk.core.DropDownCommandInput = inputs.itemById('fastener_size')
    size_props = SIZE_CONF[size_input.selectedItem.name]
    return unitsManager.evaluateExpression(size_props[name])


def cut_bore(inputs: adsk.core.CommandInputs, facet_comp: adsk.fusion.Component, limit_face: adsk.fusion.BRepFace, sketch_timeline_position: int):
    facet_point = get_point_input_value(inputs)
    bore_sketch = make_sketch(facet_comp, facet_point, "bore", sketch_timeline_position)
    bore_circle, _ = draw_dimensioned_circle(bore_sketch, facet_point, get_size_prop(inputs, 'bore_diameter'), UP.copy())
    bore_profile = find_exact_outer_profile(bore_sketch, [bore_circle])
    cut_from_point_to_face(facet_comp.features.extrudeFeatures, facet_point, limit_face, bore_profile, 'cut-bore')


def cut_head(inputs: adsk.core.CommandInputs, facet_comp: adsk.fusion.Component, limit_face: adsk.fusion.BRepFace, sketch_timeline_position: int):
    head_input: adsk.core.DropDownCommandInput = inputs.itemById('fastener_head')
    if(head_input.selectedItem.name == "None"):
        return
    
    facet_point = get_point_input_value(inputs)
    facet_head_diameter = get_size_prop(inputs, 'socket_diameter')
    head_sketch = make_sketch(facet_comp, facet_point, "head", sketch_timeline_position)
    head_circle, _ = draw_dimensioned_circle(head_sketch, facet_point, facet_head_diameter, RIGHT.copy())
    head_profile = find_exact_outer_profile(head_sketch, [head_circle])
    head_length = get_size_prop(inputs, 'socket_length')
    extrudes = facet_comp.features.extrudeFeatures
    if(not get_inverted_input_value(inputs)):
        cut_from_point_forward_distance(extrudes, facet_point, head_length, head_profile, 'head-cut')    
        return
    
    cut_from_face_backward_distance(extrudes, limit_face, head_length, head_profile, 'head-cut')
    

def cut_anchor(inputs: adsk.core.CommandInputs, facet_comp: adsk.fusion.Component, limit_face: adsk.fusion.BRepFace, sketch_timeline_position: int):
    anchor_input: adsk.core.DropDownCommandInput = inputs.itemById('fastener_anchor')
    if(anchor_input.selectedItem.name == "None"):
        return
    
    facet_point = get_point_input_value(inputs)
    anchor_sketch = make_sketch(facet_comp, facet_point, "anchor", sketch_timeline_position)
    anchor_lines, _, _, _ = draw_dimensioned_hex(anchor_sketch, facet_point, get_size_prop(inputs, 'hex_nut_diameter'), DOWN.copy())
    anchor_profile = find_exact_outer_profile(anchor_sketch, anchor_lines)
    extrudes = facet_comp.features.extrudeFeatures
    anchor_length = get_size_prop(inputs, 'hex_nut_length')
    if(get_inverted_input_value(inputs)):
        cut_from_point_forward_distance(extrudes, facet_point, anchor_length, anchor_profile, 'anchor-cut')
        return
    
    cut_from_face_backward_distance(extrudes, limit_face, anchor_length, anchor_profile, 'anchor-cut')

def cut_from_point_to_face(extrudes: adsk.fusion.ExtrudeFeatures, point: adsk.fusion.SketchPoint, face: adsk.fusion.BRepFace, profile: adsk.fusion.Profile, name: str):
    zero_offset = adsk.core.ValueInput.createByString("0 mm")
    cut_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.CutFeatureOperation)
    cut_input.setOneSideExtent(adsk.fusion.ToEntityExtentDefinition.create(face, True), adsk.fusion.ExtentDirections.PositiveExtentDirection)
    cut_input.startExtent = adsk.fusion.FromEntityStartDefinition.create(point.parentSketch.referencePlane, zero_offset)
    cut_feature = extrudes.add(cut_input)
    cut_feature.name = name
    return cut_feature

def cut_from_face_backward_distance(extrudes: adsk.fusion.ExtrudeFeatures, face: adsk.fusion.BRepFace, distance: float, profile: adsk.fusion.Profile, name: str):
    zero_offset = adsk.core.ValueInput.createByString("0 mm")
    cut_distance = adsk.core.ValueInput.createByReal(distance)
    cut_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.CutFeatureOperation)
    cut_input.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(cut_distance), adsk.fusion.ExtentDirections.PositiveExtentDirection)
    cut_input.startExtent = adsk.fusion.FromEntityStartDefinition.create(face, zero_offset)
    cut_feature = extrudes.add(cut_input)
    cut_feature.name = name
    return cut_feature


def cut_from_point_forward_distance(extrudes: adsk.fusion.ExtrudeFeatures, point: adsk.fusion.SketchPoint, distance: float, profile: adsk.fusion.Profile, name: str):
    zero_offset = adsk.core.ValueInput.createByString("0 mm")
    cut_distance = adsk.core.ValueInput.createByReal(distance)
    cut_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.CutFeatureOperation)
    cut_input.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(cut_distance), adsk.fusion.ExtentDirections.NegativeExtentDirection)
    cut_input.startExtent = adsk.fusion.FromEntityStartDefinition.create(point.parentSketch.referencePlane, zero_offset)
    cut_feature = extrudes.add(cut_input)
    cut_feature.name = name
    return cut_feature


def draw_dimensioned_hex(sketch: adsk.fusion.Sketch, center: adsk.fusion.SketchPoint, diameter: float, dimension_dir: adsk.core.Vector3D):
    projected_center: adsk.fusion.SketchPoint = sketch.project(center).item(0)
    dimension_point = projected_center.geometry.copy()
    dimension_dir.scaleBy(diameter / 4.0)
    dimension_point.translateBy(dimension_dir)
    transform = adsk.core.Matrix3D.create()
    side_count = 6
    increment = math.radians(360.0 / float(side_count))
    points: List[adsk.fusion.SketchPoint] = []
    lines: List[adsk.fusion.SketchLine] = []
    ref_point = adsk.core.Point3D.create(0.0, diameter/2.0)
    forward = FORWARD.copy()
    construction_circle, construction_dim = draw_dimensioned_circle(sketch, center, diameter, dimension_dir)
    construction_circle.isConstruction = True
    center_vector = projected_center.geometry.asVector()
    for i in range(side_count):
        transform.setToRotation(increment * i, forward, ZERO.copy())
        point = ref_point.copy() 
        point.transformBy(transform)
        point.translateBy(center_vector)
        sketch_point = sketch.sketchPoints.add(point)
        points.append(sketch_point)
    for i in range(side_count):
        point = points[i]
        last_index = i-1 if i > 0 else len(points) - 1
        point_next = points[last_index]
        line = sketch.sketchCurves.sketchLines.addByTwoPoints(point, point_next)
        lines.append(line)
        if(i  == 0):
            continue
        sketch.geometricConstraints.addEqual(lines[0], line)
    sketch.geometricConstraints.addVertical(lines[0])
    sketch.sketchDimensions.addAngularDimension(lines[0], lines[1], dimension_point)
    for i in range(side_count):
        if(i == 0):
            continue
        sketch.geometricConstraints.addTangent(lines[i], construction_circle)    
    return lines, points, construction_circle, construction_dim


def draw_dimensioned_circle(sketch: adsk.fusion.Sketch, center: adsk.fusion.SketchPoint, diameter: float, dimension_dir: adsk.core.Vector3D):
    projected_center : adsk.fusion.SketchPoint = sketch.project(center).item(0)
    dimension_point = projected_center.geometry
    dimension_dir.scaleBy(diameter / 4.0)
    dimension_point.translateBy(dimension_dir)    
    circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(projected_center.geometry.copy(), diameter / 2.0)
    sketch.geometricConstraints.addCoincident(circle.centerSketchPoint, projected_center)
    dimension = sketch.sketchDimensions.addDiameterDimension(circle, dimension_point)
    return circle, dimension


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Validate Input Event')

    args.areInputsValid = True
        

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
